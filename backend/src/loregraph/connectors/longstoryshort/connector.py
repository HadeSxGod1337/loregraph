"""LongStoryShort (longstoryshort.app) connector.

LSS has no public API. What exists (verified July 2026):
- public share pages: https://longstoryshort.app/characters/digital/{24-hex}/
- an API host api.longstoryshort.app whose GET /character/{id} answers 401
  without auth — the endpoint the public share page actually calls still has
  to be captured with browser devtools (see _CANDIDATE_ENDPOINTS below);
- an official iframe embed (built for their Owlbear integration):
  https://longstoryshort.app/iframe/characters/digital/{id}/ — the frontend
  renders it for entities carrying a character_sheet_url field.

Import therefore works from a share link when one of the candidate endpoints
answers, and always works from exported JSON — one file per character, or a
whole party in one run (``documents``). Re-importing the same character
updates the existing entity (provenance via connection_entity_links).
"""

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.longstoryshort.parser import (
    CHARACTER_SHEET_URL_KEY,
    PARTY_MEMBER_TYPE,
    parse_character,
)
from loregraph.connectors.protocols import ExternalChunk
from loregraph.exceptions import (
    CampaignError,
    ConnectorUnavailableError,
    ExternalDataParseError,
    error_code,
)
from loregraph.schemas.connection import (
    ImportedItem,
    ImportRequest,
    ImportResult,
    ItemError,
    ProbeResult,
)
from loregraph.schemas.entity import (
    EntityCreate,
    EntityFieldIn,
    EntityUpdate,
    FieldType,
)

logger = logging.getLogger(__name__)

LINK_KIND_LSS_CHARACTER = "lss_character"
SHARE_URL_RE = re.compile(
    r"longstoryshort\.app/characters/digital/(?P<char_id>[0-9a-f]{24})"
)
_API_BASE = "https://api.longstoryshort.app"
_SITE_BASE = "https://longstoryshort.app"
# Candidate JSON endpoints for a publicly shared sheet, tried in order.
# GET /character/{id} is confirmed to exist (401 unauthenticated) — the
# public variant used by the share page goes first once captured in devtools.
_CANDIDATE_ENDPOINTS = (
    "/character/{char_id}",
    "/character/shared/{char_id}",
    "/character/public/{char_id}",
)
_REQUEST_TIMEOUT_S = 10.0
_LIVE_CHUNK_LIMIT = 5


class LssConfig(BaseModel):
    """No connection-level settings yet — the connection exists to group
    imports, provenance, and (optionally) live party-state grounding."""


class LssDocument(BaseModel):
    """One uploaded export file. `name` is only ever used to say which file a
    failure came from."""

    content: str
    name: str | None = None


class LssImportPayload(BaseModel):
    share_url: str | None = None
    raw_json: str | None = None
    # A whole party in one run: one document per uploaded file. A document
    # that fails to parse is reported as an item error and the rest still
    # import — a party of five must not be lost to one bad file.
    documents: list[LssDocument] = []


class LssConnector:
    """Implements Importer, LiveSource and ConnectionProbe."""

    def __init__(self, config: LssConfig, context: ConnectorContext) -> None:
        self._config = config
        self._context = context

    # ── probe ────────────────────────────────────────────────────────────────

    async def test_connection(self) -> ProbeResult:
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
                response = await client.get(_SITE_BASE)
            if response.status_code < 500:
                return ProbeResult(ok=True, detail_code="lss_reachable")
            return ProbeResult(
                ok=False,
                detail_code="lss_unreachable",
                info={"status": str(response.status_code)},
            )
        except httpx.HTTPError as e:
            return ProbeResult(
                ok=False, detail_code="lss_unreachable", info={"error": str(e)}
            )

    # ── import ───────────────────────────────────────────────────────────────

    async def import_data(self, request: ImportRequest) -> ImportResult:
        try:
            payload = LssImportPayload.model_validate(request.payload)
        except ValidationError as e:
            raise ExternalDataParseError("longstoryshort", str(e)) from e

        result = ImportResult()
        if payload.documents:
            for index, document in enumerate(payload.documents, start=1):
                await self._import_document_safely(
                    document.content, document.name or f"#{index}", result
                )
            return result
        if payload.raw_json:
            # A single document keeps the strict contract: a syntax error is
            # the whole request's error (422), not a per-item note nobody reads.
            await self._import_document(payload.raw_json, payload.share_url, result)
            return result
        if payload.share_url:
            char_id = _extract_char_id(payload.share_url)
            if char_id is None:
                raise ExternalDataParseError(
                    "longstoryshort",
                    "share URL does not look like "
                    "longstoryshort.app/characters/digital/{id}",
                )
            share_url = _canonical_share_url(char_id)
            data = await self._fetch_character(char_id)
            await self._import_character(data, char_id, share_url, result)
            return result
        raise ExternalDataParseError(
            "longstoryshort", "payload requires share_url, raw_json or documents"
        )

    async def _import_document(
        self, document: str, share_url: str | None, result: ImportResult
    ) -> None:
        """One uploaded/pasted JSON document — which may hold a single sheet
        or a batch export of several."""
        characters = _parse_characters(document)
        # A share URL identifies exactly one sheet; it must not be stamped on
        # every character of a batch export.
        single = len(characters) == 1
        for data in characters:
            char_id = _extract_char_id(share_url) if single and share_url else None
            await self._import_character(
                data, char_id, share_url if single else None, result
            )

    async def _import_document_safely(
        self, document: str, ref: str, result: ImportResult
    ) -> None:
        try:
            await self._import_document(document, None, result)
        except asyncio.CancelledError:
            raise
        except ExternalDataParseError as e:
            logger.warning("LSS import skipped document %s: %s", ref, e)
            result.skipped += 1
            result.errors.append(ItemError(ref=ref, code=error_code(e), detail=str(e)))

    async def _fetch_character(self, char_id: str) -> dict[str, Any]:
        last_status: int | None = None
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
                for template in _CANDIDATE_ENDPOINTS:
                    url = _API_BASE + template.format(char_id=char_id)
                    response = await client.get(url)
                    last_status = response.status_code
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, dict):
                            return data
        except httpx.HTTPError as e:
            raise ConnectorUnavailableError(
                self._context.connection_name, f"LSS request failed: {e}"
            ) from e
        raise ConnectorUnavailableError(
            self._context.connection_name,
            "no public JSON endpoint answered for this sheet "
            f"(last status: {last_status}) — paste the sheet JSON instead",
        )

    async def _import_character(
        self,
        data: dict[str, Any],
        char_id: str | None,
        share_url: str | None,
        result: ImportResult,
    ) -> None:
        name, fields = parse_character(data, share_url)
        context = self._context
        existing_id = await self._find_existing(name, char_id, share_url)
        if existing_id is None:
            entity = await context.entity_service.create(
                EntityCreate(
                    type=PARTY_MEMBER_TYPE,
                    title=name,
                    fields=fields,
                    # An imported sheet is a character sheet: bind it to the
                    # party-member template right away, so the DM sees a laid
                    # out (and printable) sheet instead of a field list they
                    # have to bind by hand, once per character.
                    template_id=await self._default_template_id(),
                ),
                context.project_id,
            )
            result.created += 1
            action: Literal["created", "updated"] = "created"
        else:
            current = await context.entity_service.get_in_project(
                context.project_id, existing_id
            )
            merged = _merge_fields(current.fields, fields)
            entity = await context.entity_service.update(
                context.project_id,
                existing_id,
                EntityUpdate(
                    type=current.type,
                    title=name,
                    fields=merged,
                    # An update replaces the whole row: without this, refreshing
                    # a character from LSS would silently unbind its sheet
                    # template. A character imported before templates existed
                    # gets one on its next refresh.
                    template_id=current.template_id
                    or await self._default_template_id(),
                ),
            )
            result.updated += 1
            action = "updated"
        result.items.append(
            ImportedItem(entity_id=entity.id, title=name, action=action)
        )
        if char_id is not None:
            await context.link_store.upsert(
                context.connection_id, entity.id, char_id, LINK_KIND_LSS_CHARACTER
            )

    async def _default_template_id(self) -> str | None:
        service = self._context.template_service
        if service is None:
            return None
        template = await service.default_for_entity_type(
            self._context.project_id, PARTY_MEMBER_TYPE
        )
        return template.id if template is not None else None

    async def _find_existing(
        self, name: str, char_id: str | None, share_url: str | None
    ) -> str | None:
        context = self._context
        if char_id is not None:
            link = await context.link_store.get_by_external(
                context.connection_id, LINK_KIND_LSS_CHARACTER, char_id
            )
            if link is not None:
                return link.entity_id
        # Fall back to a title match among party members only — an NPC with
        # the same name must not be silently overwritten by a player sheet.
        party = await context.entity_store.list_entities(
            context.project_id, entity_type=PARTY_MEMBER_TYPE
        )
        for entity in party:
            if entity.title.strip().lower() == name.strip().lower():
                return entity.id
        return None

    # ── live source ──────────────────────────────────────────────────────────

    async def query(self, query: str, kind: str | None = None) -> list[ExternalChunk]:
        """Party state: re-fetches every linked character sheet and returns
        fresh facts (level/HP/stats). `query`/`kind` filter by name.

        LSS publishes no JSON endpoint we may call (see the module docstring),
        so a live fetch usually fails — and a grounding source that answers
        with nothing whenever that happens is a switch that does nothing. It
        falls back to the state of the sheet as last imported, labelled as
        such so neither the DM nor the model reads stale HP as current.
        """
        del kind  # single kind of data — character sheets
        links = await self._context.link_store.list_for_connection(
            self._context.connection_id
        )
        chunks: list[ExternalChunk] = []
        needle = query.strip().lower()
        for link in links:
            if link.external_kind != LINK_KIND_LSS_CHARACTER:
                continue
            if len(chunks) >= _LIVE_CHUNK_LIMIT:
                break
            chunk = await self._character_chunk(link.entity_id, link.external_id)
            if chunk is None or (needle and needle not in chunk.title.lower()):
                continue
            chunks.append(chunk)
        return chunks

    async def _character_chunk(
        self, entity_id: str, char_id: str
    ) -> ExternalChunk | None:
        try:
            data = await self._fetch_character(char_id)
            name, fields = parse_character(data, _canonical_share_url(char_id))
            return self._chunk(name, _fields_to_text(name, fields), live=True)
        except (ConnectorUnavailableError, ExternalDataParseError) as e:
            logger.debug("LSS live fetch failed, using last imported sheet: %s", e)
        try:
            entity = await self._context.entity_store.get(entity_id)
        except CampaignError:
            logger.warning(
                "LSS grounding skipped a sheet: entity %s is gone", entity_id
            )
            return None
        return self._chunk(
            entity.title, _fields_to_text(entity.title, entity.fields), live=False
        )

    def _chunk(self, title: str, text: str, *, live: bool) -> ExternalChunk:
        return ExternalChunk(
            source_name=self._context.connection_name,
            connector_type="longstoryshort",
            kind="character" if live else "character (as last imported)",
            title=title,
            text=text,
        )


def _extract_char_id(share_url: str) -> str | None:
    match = SHARE_URL_RE.search(share_url)
    return match.group("char_id") if match else None


def _canonical_share_url(char_id: str) -> str:
    return f"{_SITE_BASE}/characters/digital/{char_id}/"


def _parse_characters(raw: str) -> list[dict[str, Any]]:
    """Every character document inside one uploaded/pasted JSON.

    Usually exactly one (LSS exports one file per sheet), but a batch export
    — a top-level array or a ``{"characters": [...]}`` envelope — brings the
    whole party at once, and dropping all but the first would silently lose
    characters the DM asked for.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ExternalDataParseError("longstoryshort", f"invalid JSON: {e}") from e

    if isinstance(data, list):
        characters = [entry for entry in data if isinstance(entry, dict)]
        if not characters:
            raise ExternalDataParseError(
                "longstoryshort", "JSON array holds no character objects"
            )
        return characters

    if not isinstance(data, dict):
        raise ExternalDataParseError(
            "longstoryshort",
            f"expected a JSON object, got {type(data).__name__}",
        )

    # Unwrap common envelopes: {"characters": [...]}, {"data": {...}},
    # {"character": {...}}, {"sheet": {...}}, {"result": {...}}. The native
    # export's own {"jsonType": "character", "data": "<json string>"} wrapper
    # is left alone here — parse_character unwraps it (a string `data` matches
    # neither branch below).
    for wrapper_key in ("characters", "data", "character", "sheet", "result"):
        inner = data.get(wrapper_key)
        if isinstance(inner, list):
            nested = [entry for entry in inner if isinstance(entry, dict)]
            if nested:
                return nested
        elif isinstance(inner, dict):
            return [inner]
    return [data]


def _merge_fields(
    current: list[Any], incoming: list[EntityFieldIn]
) -> list[EntityFieldIn]:
    """LWW per field key: sheet facts overwrite, DM-added extra fields
    (relationship notes, secrets…) survive the refresh."""
    incoming_keys = {f.key for f in incoming}
    kept = [
        EntityFieldIn(**f.model_dump(mode="json"))
        for f in current
        if f.key not in incoming_keys
    ]
    return incoming + kept


def _fields_to_text(name: str, fields: Sequence[EntityFieldIn]) -> str:
    parts = [name]
    for field in fields:
        if field.key == CHARACTER_SHEET_URL_KEY:
            continue
        if field.field_type in (FieldType.TEXT, FieldType.NUMBER):
            parts.append(f"{field.key}: {field.value}")
    return "; ".join(parts)
