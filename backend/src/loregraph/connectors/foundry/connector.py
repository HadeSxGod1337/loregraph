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
import re
from typing import Any

from pydantic import BaseModel

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.markdown_codec import (
    MarkdownRenderOptions,
    markdown_to_prosemirror,
)
from loregraph.connectors.markdown_codec import (
    prosemirror_to_markdown as _pm_to_md,
)
from loregraph.connectors.mcp.stdio_client import McpStdioClient
from loregraph.connectors.protocols import ExternalChunk, IngestDocument
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
# Per-kind budgets, applied to EACH branch of query() independently — not
# one shared cap across every kind combined. Journals/compendium are
# relevance-ranked SEARCH results over a potentially large, mostly-
# irrelevant-beyond-the-top-few corpus, so they stay tight. Actors/items are
# a bounded, enumerable resource (this world's own actors/items, not a
# reference library) — a deliberate "list them all" chat request
# (query_external_source with kind="items"/"actors") should actually get
# them all for any normally-sized world, not silently lose most of the
# list with no indication anything was cut.
_JOURNAL_CHUNK_LIMIT = 5
_COMPENDIUM_CHUNK_LIMIT = 5
_ACTOR_CHUNK_LIMIT = 30
_ITEM_CHUNK_LIMIT = 30
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
# World-level items (the sidebar Items directory) — NOT compendium reference
# items and NOT an actor's carried items (search-character-items covers
# that separately). Previously missing entirely: query()'s "compendium"
# kind is the *reference* item library (rulebook templates), so a request
# for "this world's items" silently searched the wrong data source and
# came back nearly empty.
_TOOL_MANAGE_WORLD_ITEMS = "manage-world-items"
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
    """Implements Exporter, Importer, LiveSource, IngestSource and
    ConnectionProbe."""

    def __init__(self, config: FoundryConfig, context: ConnectorContext) -> None:
        self._config = config
        self._context = context

    async def _client(self) -> McpStdioClient:
        runtime = self._context.runtime
        config = self._config

        async def factory() -> McpStdioClient:
            client = McpStdioClient(
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

    async def _try_create_npc(self, client: McpStdioClient, entity: EntityOut) -> None:
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
        """Pull actors as npc entities. Journal import is deliberately out of
        scope here: Loregraph journals are what we push there, and pulling
        them back would round-trip our own exports as duplicates. That stays
        correct — a FOREIGN world's journals are the migration path's job
        instead (see ingest_documents), which reads them in full and routes
        them through AI extraction plus human review."""
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
        client: McpStdioClient,
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
        # The bridge's real schema requires "identifier" (name or id) — not
        # "characterName". external_id (the Foundry document id from
        # list-characters) is used rather than name: this world has many
        # same-named actors ("Маг" x3, "Бальтазар" x2, ...), and by id is
        # unambiguous where by-name could resolve to the wrong actor.
        detail = await client.call_tool(
            _TOOL_GET_CHARACTER, {"identifier": external_id}
        )
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
        """Each branch applies its OWN budget (see the _*_CHUNK_LIMIT
        constants) instead of one shared cap sliced across every kind
        combined — a deliberate, single-kind request (e.g. kind="items" for
        "list every item") gets that kind's full budget, not a fraction of
        a budget shared with journals/actors it never asked about."""
        client = await self._client()
        chunks: list[ExternalChunk] = []
        if kind in (None, "journals"):
            # The bridge's real schema requires "searchQuery" — not "query".
            response = await client.call_tool(
                _TOOL_SEARCH_JOURNALS, {"searchQuery": query}
            )
            chunks.extend(self._journal_chunks(response)[:_JOURNAL_CHUNK_LIMIT])
        if kind in (None, "actors", "characters"):
            response = await client.call_tool(_TOOL_LIST_CHARACTERS, {})
            needle = query.strip().lower()
            actor_chunks: list[ExternalChunk] = []
            for descriptor in _character_descriptors(response):
                name = descriptor.get("name")
                if not isinstance(name, str):
                    continue
                if needle and needle not in name.lower():
                    continue
                actor_chunks.extend(self._to_chunks([descriptor], "character", 1))
                if len(actor_chunks) >= _ACTOR_CHUNK_LIMIT:
                    break
            chunks.extend(actor_chunks)
        if kind in (None, "items", "world_items"):
            # This world's own standalone items (armor/weapons/loot in the
            # sidebar Items directory) — distinct from "compendium" (the
            # reference rulebook library) and from an actor's own carried
            # items (search-character-items, not this method's concern).
            args: dict[str, Any] = {"action": "list"}
            if query.strip():
                args["nameFilter"] = query.strip()
            response = await client.call_tool(_TOOL_MANAGE_WORLD_ITEMS, args)
            chunks.extend(self._world_item_chunks(response)[:_ITEM_CHUNK_LIMIT])
        if kind == "compendium":
            response = await client.call_tool(_TOOL_SEARCH_COMPENDIUM, {"query": query})
            chunks.extend(
                self._to_chunks(response, "compendium", _COMPENDIUM_CHUNK_LIMIT)
            )
        return chunks

    def _journal_chunks(self, response: Any) -> list[ExternalChunk]:
        """search-journals has a distinct shape from the other tools (a
        real, live-verified response, not a guess — see the comment on the
        query() call site): `{results: [{name, matchedPages: [{pageName,
        contentSnippet}, ...]}, ...]}`. The match itself is only a
        (journalId, pageId) locator with a truncated preview — no full-page
        endpoint is used here, the snippet is what grounds the answer, same
        budget as every other live source (never a full document dump)."""
        results = response.get("results") if isinstance(response, dict) else None
        if not isinstance(results, list):
            return []
        chunks: list[ExternalChunk] = []
        for journal in results:
            if not isinstance(journal, dict):
                continue
            journal_name = str(journal.get("name") or "Journal")
            pages = journal.get("matchedPages")
            if not isinstance(pages, list):
                continue
            for page in pages:
                if not isinstance(page, dict):
                    continue
                snippet = page.get("contentSnippet")
                if not isinstance(snippet, str) or not snippet.strip():
                    continue
                page_name = page.get("pageName")
                title = f"{journal_name} — {page_name}" if page_name else journal_name
                chunks.append(
                    ExternalChunk(
                        source_name=self._context.connection_name,
                        connector_type="foundry",
                        kind="journal",
                        title=title,
                        text=_strip_html(snippet)[:_LIVE_TEXT_LIMIT],
                    )
                )
        return chunks

    def _world_item_chunks(self, response: Any) -> list[ExternalChunk]:
        """manage-world-items(action="list") shape (live-verified):
        `{items: [{id, name, type, img, folderId, folderName}], total}` —
        listing only, no description text (there is no "get one world item
        with full details" action on this tool, only create/list/update/
        add-to-actor)."""
        items = response.get("items") if isinstance(response, dict) else None
        if not isinstance(items, list):
            return []
        chunks: list[ExternalChunk] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            item_type = item.get("type")
            folder = item.get("folderName")
            detail_bits = [str(item_type)] if isinstance(item_type, str) else []
            if isinstance(folder, str) and folder:
                detail_bits.append(f"folder: {folder}")
            chunks.append(
                ExternalChunk(
                    source_name=self._context.connection_name,
                    connector_type="foundry",
                    kind="item",
                    title=name,
                    text=", ".join(detail_bits) or "world item",
                )
            )
        return chunks

    def _to_chunks(self, response: Any, kind: str, limit: int) -> list[ExternalChunk]:
        records: list[Any]
        if isinstance(response, list):
            records = response
        elif isinstance(response, dict):
            nested = response.get("results") or response.get("journals")
            records = nested if isinstance(nested, list) else [response]
        else:
            records = [response]
        chunks: list[ExternalChunk] = []
        for record in records[:limit]:
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

    # ── ingest (IngestSource) ────────────────────────────────────────────────

    async def ingest_documents(self) -> list[IngestDocument]:
        """Dump this world's content as plain text for the AI migration
        pipeline (agent/import_graph.py) — the "bring my existing Foundry
        world into the graph" path.

        Deliberately broader than import_data(): that one is a deterministic
        round-trip of what WE exported (actors only, journals skipped so our
        own exports don't come back as duplicates). Migration is the opposite
        case — the world was never ours, so its journals are the main prize
        and are pulled in FULL (page by page), not as search snippets.

        One document per journal (pages as `## sections`), plus one aggregate
        document each for actors and world items — those are short, uniform
        records, so aggregating keeps the extractor's windows well packed
        instead of one call per one-line record."""
        client = await self._client()
        documents: list[IngestDocument] = []
        documents.extend(await self._ingest_journals(client))
        actors = await self._ingest_actors(client)
        if actors is not None:
            documents.append(actors)
        items = await self._ingest_items(client)
        if items is not None:
            documents.append(items)
        return documents

    async def _ingest_journals(self, client: McpStdioClient) -> list[IngestDocument]:
        listing = await client.call_tool(_TOOL_LIST_JOURNALS, {})
        journals = listing.get("journals") if isinstance(listing, dict) else None
        if not isinstance(journals, list):
            return []
        documents: list[IngestDocument] = []
        for journal in journals:
            if not isinstance(journal, dict):
                continue
            journal_id = journal.get("id")
            name = str(journal.get("name") or "Journal")
            pages = journal.get("pages")
            if not isinstance(journal_id, str) or not isinstance(pages, list):
                continue
            sections: list[str] = []
            for page in pages:
                if not isinstance(page, dict):
                    continue
                page_id = page.get("id")
                if not isinstance(page_id, str):
                    continue
                page_name = str(page.get("name") or "")
                text = await self._journal_page_text(client, journal_id, page_id)
                if text:
                    heading = f"## {page_name}\n\n" if page_name else ""
                    sections.append(f"{heading}{text}")
            if sections:
                documents.append(
                    IngestDocument(
                        external_id=journal_id,
                        title=name,
                        text="\n\n".join(sections),
                        kind="journal",
                    )
                )
        return documents

    async def _journal_page_text(
        self, client: McpStdioClient, journal_id: str, page_id: str
    ) -> str:
        """Full page content (not the truncated search snippet query() uses).
        One unreadable page must not sink a whole migration, so a failure is
        logged and skipped."""
        try:
            response = await client.call_tool(
                _TOOL_LIST_JOURNALS, {"journalId": journal_id, "pageId": page_id}
            )
        except ConnectorUnavailableError:
            logger.warning(
                "Skipping unreadable Foundry journal page %s/%s",
                journal_id,
                page_id,
                exc_info=True,
            )
            return ""
        page = response.get("page") if isinstance(response, dict) else None
        content = page.get("content") if isinstance(page, dict) else None
        return _strip_html(content) if isinstance(content, str) else ""

    async def _ingest_actors(self, client: McpStdioClient) -> IngestDocument | None:
        response = await client.call_tool(_TOOL_LIST_CHARACTERS, {})
        blocks: list[str] = []
        for descriptor in _character_descriptors(response):
            name = descriptor.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            external_id = str(descriptor.get("id") or descriptor.get("_id") or name)
            try:
                detail = await client.call_tool(
                    _TOOL_GET_CHARACTER, {"identifier": external_id}
                )
            except ConnectorUnavailableError:
                logger.warning("Skipping unreadable actor %s", name, exc_info=True)
                continue
            blocks.append(_actor_text(name, detail))
        if not blocks:
            return None
        return IngestDocument(
            external_id="actors",
            title="Characters and NPCs",
            text="\n\n".join(blocks),
            kind="actor",
        )

    async def _ingest_items(self, client: McpStdioClient) -> IngestDocument | None:
        response = await client.call_tool(_TOOL_MANAGE_WORLD_ITEMS, {"action": "list"})
        items = response.get("items") if isinstance(response, dict) else None
        if not isinstance(items, list):
            return None
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            item_type = item.get("type")
            suffix = f" ({item_type})" if isinstance(item_type, str) else ""
            lines.append(f"- {name}{suffix}")
        if not lines:
            return None
        return IngestDocument(
            external_id="items",
            title="World items",
            text="\n".join(lines),
            kind="item",
        )


def _actor_text(name: str, detail: Any) -> str:
    """Readable block for one actor. get-character is deliberately
    description-free (no biography/class/race — see _actor_fields), so this
    is stats plus carried items; the extractor still gets a named character
    it can relate to the journals' narrative."""
    if not isinstance(detail, dict):
        return f"### {name}"
    stats = detail.get("stats")
    stats = stats if isinstance(stats, dict) else detail
    parts: list[str] = [f"### {name}"]
    actor_type = detail.get("type")
    if isinstance(actor_type, str) and actor_type:
        parts.append(f"type: {actor_type}")
    for key, label in (("level", "level"), ("challengeRating", "CR")):
        value = stats.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool) and value:
            parts.append(f"{label}: {value}")
    armor_class = stats.get("armorClass")
    if isinstance(armor_class, int | float) and not isinstance(armor_class, bool):
        parts.append(f"AC: {armor_class}")
    hit_points = stats.get("hitPoints")
    max_hp = hit_points.get("max") if isinstance(hit_points, dict) else None
    if isinstance(max_hp, int | float) and not isinstance(max_hp, bool):
        parts.append(f"HP: {max_hp}")
    items = detail.get("items")
    if isinstance(items, list):
        names = [
            str(item["name"])
            for item in items
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        if names:
            parts.append("equipment: " + ", ".join(names))
    return "\n".join(parts)


def _text_field(entity: EntityOut, key: str) -> str | None:
    for field in entity.fields:
        if field.key == key and field.field_type is FieldType.TEXT:
            value = field.value
            return value if isinstance(value, str) and value.strip() else None
    return None


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """search-journals content snippets are truncated ProseMirror/TipTap
    HTML (<p data-start="...">...), not plain text — strip tags so what
    reaches the model (and gets cited to the game master) reads as prose,
    not markup soup."""
    return " ".join(_HTML_TAG_RE.sub(" ", text).split())


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
    """get-character (the bridge tool) is deliberately description-free —
    "optimized for minimal token usage": no class/race/alignment/biography,
    stats nested under `stats`/`basicInfo` rather than flat top-level keys.
    Full item/action/effect descriptions need a separate get-character-
    entity call per item, which this bulk import doesn't do (same
    "no round-tripping full detail" scope call as the module docstring's
    journal-import note)."""
    fields: list[EntityFieldIn] = []
    stats = detail.get("stats")
    stats = stats if isinstance(stats, dict) else detail

    for key, target in (("level", "level"), ("challengeRating", "cr")):
        value = stats.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool) and value:
            fields.append(
                EntityFieldIn(key=target, field_type=FieldType.NUMBER, value=value)
            )
    ac = stats.get("armorClass")
    if isinstance(ac, int | float) and not isinstance(ac, bool):
        fields.append(EntityFieldIn(key="ac", field_type=FieldType.NUMBER, value=ac))
    hit_points = stats.get("hitPoints")
    max_hp = hit_points.get("max") if isinstance(hit_points, dict) else None
    if isinstance(max_hp, int | float) and not isinstance(max_hp, bool):
        fields.append(
            EntityFieldIn(key="hp", field_type=FieldType.NUMBER, value=max_hp)
        )

    items = detail.get("items")
    if isinstance(items, list):
        names = [
            str(item["name"])
            for item in items
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        if names:
            fields.append(
                EntityFieldIn(key="equipment", field_type=FieldType.TAG, value=names)
            )
    return fields


def _compact_json(record: dict[str, Any]) -> str:
    parts = []
    for key, value in record.items():
        if isinstance(value, str | int | float) and not isinstance(value, bool):
            parts.append(f"{key}: {value}")
    return "; ".join(parts)
