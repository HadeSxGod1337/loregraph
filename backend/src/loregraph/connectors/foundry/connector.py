"""Foundry VTT connector via the community Foundry MCP Bridge
(adambdooley/foundry-vtt-mcp): Loregraph spawns the bridge's stdio MCP
server, which talks WebSocket (localhost:31415 by default) to the Foundry
module. Foundry may simply be off — every failure surfaces as
ConnectorUnavailableError (502) and, on the agent path, degrades.

Export strategy: every entity becomes a quest journal (markdown content the
bridge converts for Foundry); NPCs additionally try ``dnd5e-create-npc``
when the bridge exposes it, falling back to a journal. Returned document ids
are stored as provenance so re-exports update instead of duplicating.
"""

import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.foundry.mcp_client import FoundryMcpClient
from loregraph.connectors.markdown_codec import (
    MarkdownRenderOptions,
    markdown_to_prosemirror,
)
from loregraph.connectors.markdown_codec import (
    prosemirror_to_markdown as _pm_to_md,
)
from loregraph.connectors.protocols import ExternalChunk
from loregraph.exceptions import (
    ConnectorUnavailableError,
    EntityNotFoundError,
    error_code,
)
from loregraph.schemas.connection import (
    ExportPreview,
    ExportPreviewItem,
    ExportRequest,
    ExportResult,
    ImportRequest,
    ImportResult,
    ItemError,
    ProbeResult,
)
from loregraph.schemas.entity import (
    EntityCreate,
    EntityFieldIn,
    EntityOut,
    FieldType,
)

logger = logging.getLogger(__name__)

LINK_KIND_JOURNAL = "journal"
LINK_KIND_ACTOR = "actor"
NPC_TYPE = "npc"
_LIVE_CHUNK_LIMIT = 5
_LIVE_TEXT_LIMIT = 600

# Tool names of the Foundry MCP Bridge (verified against its README).
_TOOL_WORLD_INFO = "get-world-info"
_TOOL_CREATE_JOURNAL = "create-quest-journal"
_TOOL_UPDATE_JOURNAL = "update-quest-journal"
_TOOL_SEARCH_JOURNALS = "search-journals"
_TOOL_LIST_JOURNALS = "list-journals"
_TOOL_LIST_CHARACTERS = "list-characters"
_TOOL_GET_CHARACTER = "get-character"
_TOOL_SEARCH_COMPENDIUM = "search-compendium"
_TOOL_CREATE_NPC = "dnd5e-create-npc"


class FoundryConfig(BaseModel):
    # Path to the bridge's built entrypoint:
    # /path/to/foundry-vtt-mcp/packages/mcp-server/dist/index.js
    mcp_server_path: str
    node_command: str = "node"
    foundry_host: str = "localhost"
    foundry_port: int = 31415
    request_timeout_s: float = 15.0


class FoundryConnector:
    """Implements Exporter, Importer, LiveSource and ConnectionProbe."""

    def __init__(self, config: FoundryConfig, context: ConnectorContext) -> None:
        self._config = config
        self._context = context

    async def _client(self) -> FoundryMcpClient:
        runtime = self._context.runtime
        config = self._config

        async def factory() -> FoundryMcpClient:
            client = FoundryMcpClient(
                connection_name=self._context.connection_name,
                command=config.node_command,
                args=[config.mcp_server_path],
                env={
                    "FOUNDRY_HOST": config.foundry_host,
                    "FOUNDRY_PORT": str(config.foundry_port),
                },
                timeout_s=config.request_timeout_s,
            )
            await client.start()
            return client

        if runtime is None:
            # No runtime (unit-test context): a throwaway client still works,
            # it just won't be reused.
            return await factory()
        return await runtime.get_or_create(self._context.connection_id, factory)

    # ── probe ────────────────────────────────────────────────────────────────

    async def test_connection(self) -> ProbeResult:
        try:
            client = await self._client()
            info = await client.call_tool(_TOOL_WORLD_INFO, {})
        except ConnectorUnavailableError as e:
            return ProbeResult(
                ok=False, detail_code="foundry_unreachable", info={"error": str(e)}
            )
        details: dict[str, str] = {}
        if isinstance(info, dict):
            for key in ("title", "world", "system", "version"):
                value = info.get(key)
                if isinstance(value, str):
                    details[key] = value
        return ProbeResult(ok=True, detail_code="foundry_ok", info=details)

    # ── export ───────────────────────────────────────────────────────────────

    async def preview_export(self, request: ExportRequest) -> ExportPreview:
        entities, id_to_title, edges = await self._load_entities(request)
        links = await self._journal_links()
        items = [
            ExportPreviewItem(
                entity_id=entity.id,
                title=entity.title,
                action="update" if entity.id in links else "create",
                target=f"journal: {entity.title}",
                rendered=self._entity_markdown(entity, edges, id_to_title),
            )
            for entity in entities
        ]
        return ExportPreview(items=items)

    async def export(self, request: ExportRequest) -> ExportResult:
        entities, id_to_title, edges = await self._load_entities(request)
        links = await self._journal_links()
        client = await self._client()
        result = ExportResult()
        for entity in entities:
            content = self._entity_markdown(entity, edges, id_to_title)
            try:
                existing_journal = links.get(entity.id)
                if existing_journal is not None:
                    await client.call_tool(
                        _TOOL_UPDATE_JOURNAL,
                        {
                            "journalId": existing_journal,
                            "title": entity.title,
                            "content": content,
                        },
                    )
                    result.updated += 1
                else:
                    response = await client.call_tool(
                        _TOOL_CREATE_JOURNAL,
                        {"title": entity.title, "content": content},
                    )
                    journal_id = _extract_id(response) or entity.title
                    await self._context.link_store.upsert(
                        self._context.connection_id,
                        entity.id,
                        journal_id,
                        LINK_KIND_JOURNAL,
                    )
                    result.created += 1
                    if entity.type == NPC_TYPE:
                        await self._try_create_npc(client, entity)
            except asyncio.CancelledError:
                raise
            except ConnectorUnavailableError as e:
                logger.warning(
                    "Foundry export failed for entity %s", entity.id, exc_info=True
                )
                result.errors.append(
                    ItemError(ref=entity.title, code=error_code(e), detail=str(e))
                )
        return result

    async def _try_create_npc(
        self, client: FoundryMcpClient, entity: EntityOut
    ) -> None:
        """Best effort: an actor next to the journal when the bridge has the
        dnd5e tool. Failure is logged, never an export error — the journal
        already carries the content."""
        if _TOOL_CREATE_NPC not in await client.tool_names():
            return
        summary = _text_field(entity, "summary") or entity.title
        try:
            response = await client.call_tool(
                _TOOL_CREATE_NPC, {"name": entity.title, "description": summary}
            )
        except ConnectorUnavailableError:
            logger.warning(
                "dnd5e-create-npc failed for %s; journal export stands",
                entity.title,
                exc_info=True,
            )
            return
        actor_id = _extract_id(response)
        if actor_id is not None:
            await self._context.link_store.upsert(
                self._context.connection_id, entity.id, actor_id, LINK_KIND_ACTOR
            )

    async def _load_entities(
        self, request: ExportRequest
    ) -> tuple[list[EntityOut], dict[str, str], list[Any]]:
        context = self._context
        all_entities = await context.entity_store.list_entities(context.project_id)
        if request.entity_ids is None:
            entities = all_entities
        else:
            by_id = {e.id: e for e in all_entities}
            missing = [i for i in request.entity_ids if i not in by_id]
            if missing:
                raise EntityNotFoundError(missing[0])
            entities = [by_id[i] for i in request.entity_ids]
        edges = await context.edge_store.list_all(context.project_id)
        return entities, {e.id: e.title for e in all_entities}, edges

    async def _journal_links(self) -> dict[str, str]:
        links = await self._context.link_store.list_for_connection(
            self._context.connection_id
        )
        return {
            link.entity_id: link.external_id
            for link in links
            if link.external_kind == LINK_KIND_JOURNAL
        }

    def _entity_markdown(
        self, entity: EntityOut, edges: list[Any], id_to_title: dict[str, str]
    ) -> str:
        options = MarkdownRenderOptions(
            resolve_entity_link=lambda entity_id, label: id_to_title.get(
                entity_id, label
            )
        )
        parts = [f"# {entity.title}", f"*{entity.type}*"]
        for field in entity.fields:
            match field.field_type:
                case FieldType.TEXT | FieldType.NUMBER:
                    parts.append(f"## {field.key}\n\n{field.value}")
                case FieldType.TAG:
                    if isinstance(field.value, list) and field.value:
                        parts.append(
                            f"## {field.key}\n\n"
                            + ", ".join(str(v) for v in field.value)
                        )
                case FieldType.RICH_TEXT:
                    parts.append(f"## {field.key}\n\n{_pm_to_md(field.value, options)}")
                case FieldType.ATTACHMENT:
                    pass  # binary refs don't travel to Foundry journals
        relationship_lines = []
        for edge in edges:
            if edge.source_entity_id == entity.id:
                other = id_to_title.get(edge.target_entity_id)
                if other:
                    suffix = f" — {edge.label}" if edge.label else ""
                    relationship_lines.append(f"- {edge.type} → {other}{suffix}")
            elif edge.target_entity_id == entity.id:
                other = id_to_title.get(edge.source_entity_id)
                if other:
                    suffix = f" — {edge.label}" if edge.label else ""
                    relationship_lines.append(f"- {edge.type} ← {other}{suffix}")
        if relationship_lines:
            parts.append("## Relationships\n\n" + "\n".join(relationship_lines))
        return "\n\n".join(parts)

    # ── import ───────────────────────────────────────────────────────────────

    async def import_data(self, request: ImportRequest) -> ImportResult:
        """Pull actors as npc entities. Journal import is deliberately not in
        the first iteration: Loregraph journals are what we push there, and
        pulling them back would round-trip our own exports as duplicates."""
        del request
        client = await self._client()
        result = ImportResult()
        characters = await client.call_tool(_TOOL_LIST_CHARACTERS, {})
        for descriptor in _character_descriptors(characters):
            name = descriptor.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            external_id = str(descriptor.get("id") or descriptor.get("_id") or name)
            try:
                await self._import_actor(client, name, external_id, result)
            except asyncio.CancelledError:
                raise
            except ConnectorUnavailableError as e:
                result.errors.append(
                    ItemError(ref=name, code=error_code(e), detail=str(e))
                )
        return result

    async def _import_actor(
        self,
        client: FoundryMcpClient,
        name: str,
        external_id: str,
        result: ImportResult,
    ) -> None:
        context = self._context
        existing_link = await context.link_store.get_by_external(
            context.connection_id, LINK_KIND_ACTOR, external_id
        )
        if existing_link is not None:
            result.skipped += 1
            return
        detail = await client.call_tool(_TOOL_GET_CHARACTER, {"characterName": name})
        fields: list[EntityFieldIn] = [
            EntityFieldIn(
                key="tags", field_type=FieldType.TAG, value=["foundry-import"]
            )
        ]
        if isinstance(detail, dict):
            fields.extend(_actor_fields(detail))
        elif isinstance(detail, str) and detail.strip():
            fields.append(
                EntityFieldIn(
                    key="description",
                    field_type=FieldType.RICH_TEXT,
                    value=markdown_to_prosemirror(detail),
                )
            )
        entity = await context.entity_service.create(
            EntityCreate(type=NPC_TYPE, title=name.strip(), fields=fields),
            context.project_id,
        )
        await context.link_store.upsert(
            context.connection_id, entity.id, external_id, LINK_KIND_ACTOR
        )
        result.created += 1

    # ── live source ──────────────────────────────────────────────────────────

    async def query(self, query: str, kind: str | None = None) -> list[ExternalChunk]:
        client = await self._client()
        chunks: list[ExternalChunk] = []
        if kind in (None, "journals"):
            response = await client.call_tool(_TOOL_SEARCH_JOURNALS, {"query": query})
            chunks.extend(self._to_chunks(response, "journal"))
        if kind in (None, "actors", "characters"):
            response = await client.call_tool(_TOOL_LIST_CHARACTERS, {})
            needle = query.strip().lower()
            for descriptor in _character_descriptors(response):
                name = descriptor.get("name")
                if not isinstance(name, str):
                    continue
                if needle and needle not in name.lower():
                    continue
                chunks.extend(self._to_chunks([descriptor], "character"))
        if kind == "compendium":
            response = await client.call_tool(_TOOL_SEARCH_COMPENDIUM, {"query": query})
            chunks.extend(self._to_chunks(response, "compendium"))
        return chunks[:_LIVE_CHUNK_LIMIT]

    def _to_chunks(self, response: Any, kind: str) -> list[ExternalChunk]:
        records: list[Any]
        if isinstance(response, list):
            records = response
        elif isinstance(response, dict):
            nested = response.get("results") or response.get("journals")
            records = nested if isinstance(nested, list) else [response]
        else:
            records = [response]
        chunks: list[ExternalChunk] = []
        for record in records[:_LIVE_CHUNK_LIMIT]:
            if isinstance(record, dict):
                title = str(record.get("name") or record.get("title") or kind)
                text = _compact_json(record)
            else:
                title = kind
                text = str(record)
            chunks.append(
                ExternalChunk(
                    source_name=self._context.connection_name,
                    connector_type="foundry",
                    kind=kind,
                    title=title,
                    text=text[:_LIVE_TEXT_LIMIT],
                )
            )
        return chunks


def _text_field(entity: EntityOut, key: str) -> str | None:
    for field in entity.fields:
        if field.key == key and field.field_type is FieldType.TEXT:
            value = field.value
            return value if isinstance(value, str) and value.strip() else None
    return None


def _character_descriptors(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    if isinstance(response, dict):
        nested = response.get("characters") or response.get("results")
        if isinstance(nested, list):
            return [r for r in nested if isinstance(r, dict)]
        return [response]
    return []


def _extract_id(response: Any) -> str | None:
    if isinstance(response, dict):
        for key in ("id", "_id", "journalId", "actorId", "uuid"):
            value = response.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _actor_fields(detail: dict[str, Any]) -> list[EntityFieldIn]:
    fields: list[EntityFieldIn] = []
    for key in ("class", "race", "type", "alignment"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            fields.append(
                EntityFieldIn(key=key, field_type=FieldType.TEXT, value=value.strip())
            )
    for key in ("level", "hp", "ac", "cr"):
        value = detail.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            fields.append(
                EntityFieldIn(key=key, field_type=FieldType.NUMBER, value=value)
            )
    biography = detail.get("biography") or detail.get("description")
    if isinstance(biography, str) and biography.strip():
        fields.append(
            EntityFieldIn(
                key="biography",
                field_type=FieldType.RICH_TEXT,
                value=markdown_to_prosemirror(biography),
            )
        )
    return fields


def _compact_json(record: dict[str, Any]) -> str:
    parts = []
    for key, value in record.items():
        if isinstance(value, str | int | float) and not isinstance(value, bool):
            parts.append(f"{key}: {value}")
    return "; ".join(parts)
