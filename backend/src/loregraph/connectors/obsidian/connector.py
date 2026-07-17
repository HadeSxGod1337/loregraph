"""Obsidian (Markdown vault) connector.

Export: one ``.md`` note per entity with YAML frontmatter, ``[[wikilinks]]``
for entity links/relationships and copied attachments — the vault's graph
view mirrors the Loregraph graph out of the box.

Import: manual, DM-triggered. Walks the configured subfolder, upserts
entities by ``loregraph_id`` frontmatter, then by title, else creates.
Conflict strategy is last-write-wins; the ImportResult report is the audit
trail (a merge UI is deliberately out of scope for the first iteration).
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.markdown_codec import (
    MarkdownRenderOptions,
    markdown_to_prosemirror,
    prosemirror_to_markdown,
    resolve_entity_link_ids,
)
from loregraph.connectors.obsidian.frontmatter import compose_note, parse_note
from loregraph.exceptions import (
    CampaignError,
    ConnectorUnavailableError,
    EntityNotFoundError,
    ExternalDataParseError,
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
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import (
    EntityCreate,
    EntityFieldIn,
    EntityOut,
    EntityUpdate,
    FieldType,
)

logger = logging.getLogger(__name__)

ATTACHMENTS_SUBFOLDER = "_attachments"
LINK_KIND_MD_FILE = "md_file"
# TEXT values short enough to live in frontmatter; longer ones become a body
# section so the note stays readable in Obsidian.
FRONTMATTER_TEXT_LIMIT = 120
# Frontmatter keys owned by the exporter — entity fields with these keys stay
# in the body so a round trip can't corrupt provenance metadata.
RESERVED_FRONTMATTER_KEYS = frozenset({"loregraph_id", "type", "tags"})
RELATIONSHIPS_HEADING = "Relationships"

_FILENAME_UNSAFE_RE = re.compile(r'[\\/:*?"<>|\[\]#^]')
_RELATIONSHIP_LINE_RE = re.compile(
    r"^-\s*(?P<type>\S+)\s*(?P<arrow>→|←|->|<-)\s*"
    r"\[\[(?P<target>[^\]]+)\]\](?:\s*—\s*(?P<label>.*))?$"
)
_FILES_URL_RE = re.compile(r"^/files/(?P<entity_id>[0-9a-f]{32})/(?P<stored>.+)$")


class ObsidianConfig(BaseModel):
    vault_path: str
    subfolder: str = "Loregraph"
    export_attachments: bool = True


class ObsidianConnector:
    """Implements Exporter, Importer and ConnectionProbe over a local vault."""

    def __init__(self, config: ObsidianConfig, context: ConnectorContext) -> None:
        self._config = config
        self._context = context

    @property
    def _root(self) -> Path:
        return Path(self._config.vault_path) / self._config.subfolder

    # ── probe ────────────────────────────────────────────────────────────────

    async def test_connection(self) -> ProbeResult:
        vault = Path(self._config.vault_path)

        def check() -> ProbeResult:
            if not vault.exists():
                return ProbeResult(
                    ok=False,
                    detail_code="vault_path_missing",
                    info={"path": str(vault)},
                )
            if not vault.is_dir():
                return ProbeResult(
                    ok=False,
                    detail_code="vault_not_directory",
                    info={"path": str(vault)},
                )
            probe_file = vault / ".loregraph-write-probe"
            try:
                probe_file.write_text("", encoding="utf-8")
                probe_file.unlink()
            except OSError:
                return ProbeResult(
                    ok=False,
                    detail_code="vault_not_writable",
                    info={"path": str(vault)},
                )
            return ProbeResult(
                ok=True, detail_code="vault_ok", info={"path": str(vault)}
            )

        return await asyncio.to_thread(check)

    # ── export ───────────────────────────────────────────────────────────────

    async def preview_export(self, request: ExportRequest) -> ExportPreview:
        plan = await self._plan_export(request)
        return ExportPreview(
            items=[
                ExportPreviewItem(
                    entity_id=entity.id,
                    title=entity.title,
                    action="update" if entity.id in plan.existing_links else "create",
                    target=relpath,
                    rendered=rendered,
                )
                for entity, relpath, rendered in plan.items
            ]
        )

    async def export(self, request: ExportRequest) -> ExportResult:
        plan = await self._plan_export(request)
        result = ExportResult()
        for entity, relpath, rendered in plan.items:
            try:
                await self._write_note(entity, relpath, rendered, plan.existing_links)
                if entity.id in plan.existing_links:
                    result.updated += 1
                else:
                    result.created += 1
                await self._context.link_store.upsert(
                    self._context.connection_id,
                    entity.id,
                    relpath,
                    LINK_KIND_MD_FILE,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    "Obsidian export failed for entity %s", entity.id, exc_info=True
                )
                result.errors.append(
                    ItemError(ref=entity.title, code=error_code(e), detail=str(e))
                )
        return result

    async def _plan_export(self, request: ExportRequest) -> "_ExportPlan":
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
        id_to_title = {e.id: e.title for e in all_entities}
        # Duplicate titles anywhere in the project get an id suffix so two
        # entities can never fight over one note file.
        title_counts: dict[str, int] = {}
        for e in all_entities:
            key = e.title.strip().lower()
            title_counts[key] = title_counts.get(key, 0) + 1
        links = await context.link_store.list_for_connection(context.connection_id)
        existing_links = {
            link.entity_id: link.external_id
            for link in links
            if link.external_kind == LINK_KIND_MD_FILE
        }
        items: list[tuple[EntityOut, str, str]] = []
        for entity in entities:
            relpath = self._note_relpath(entity, title_counts)
            rendered = self._render_note(entity, edges, id_to_title)
            items.append((entity, relpath, rendered))
        return _ExportPlan(items, existing_links)

    def _note_relpath(self, entity: EntityOut, title_counts: dict[str, int]) -> str:
        filename = _sanitize_filename(entity.title) or "Untitled"
        if title_counts.get(entity.title.strip().lower(), 0) > 1:
            filename = f"{filename} ({entity.id[:8]})"
        type_dir = _sanitize_filename(entity.type.strip().capitalize()) or "Other"
        return f"{type_dir}/{filename}.md"

    def _render_note(
        self,
        entity: EntityOut,
        edges: list[Any],
        id_to_title: dict[str, str],
    ) -> str:
        options = MarkdownRenderOptions(
            # Resolve by id against live titles; stored labels go stale.
            resolve_entity_link=lambda entity_id, label: id_to_title.get(
                entity_id, label
            ),
            render_image=self._render_image_markdown,
        )
        frontmatter: dict[str, Any] = {
            "loregraph_id": entity.id,
            "type": entity.type,
        }
        tags: list[str] = []
        body_sections: list[str] = []
        for field in entity.fields:
            match field.field_type:
                case FieldType.TAG:
                    if isinstance(field.value, list):
                        tags.extend(str(v) for v in field.value)
                case FieldType.NUMBER:
                    if field.key not in RESERVED_FRONTMATTER_KEYS:
                        frontmatter[field.key] = field.value
                    else:
                        body_sections.append(f"## {field.key}\n\n{field.value}")
                case FieldType.TEXT:
                    value = str(field.value)
                    if (
                        len(value) <= FRONTMATTER_TEXT_LIMIT
                        and "\n" not in value
                        and field.key not in RESERVED_FRONTMATTER_KEYS
                        and field.key not in frontmatter
                    ):
                        frontmatter[field.key] = value
                    else:
                        body_sections.append(f"## {field.key}\n\n{value}")
                case FieldType.RICH_TEXT:
                    markdown = prosemirror_to_markdown(field.value, options)
                    body_sections.append(f"## {field.key}\n\n{markdown}")
                case FieldType.ATTACHMENT:
                    embed = self._attachment_embed(field.value)
                    if embed is not None:
                        body_sections.append(f"## {field.key}\n\n{embed}")
        if tags:
            frontmatter["tags"] = tags

        body_parts = [f"# {entity.title}"]
        if entity.icon is not None and self._config.export_attachments:
            icon_embed = self._files_url_to_embed(entity.icon.url)
            if icon_embed is not None:
                body_parts.append(icon_embed)
        body_parts.extend(body_sections)

        relationship_lines = self._relationship_lines(entity, edges, id_to_title)
        if relationship_lines:
            body_parts.append(
                f"## {RELATIONSHIPS_HEADING}\n\n" + "\n".join(relationship_lines)
            )
        return compose_note(frontmatter, "\n\n".join(body_parts))

    def _relationship_lines(
        self, entity: EntityOut, edges: list[Any], id_to_title: dict[str, str]
    ) -> list[str]:
        lines: list[str] = []
        for edge in edges:
            if edge.source_entity_id == entity.id:
                other = id_to_title.get(edge.target_entity_id)
                arrow = "→"
            elif edge.target_entity_id == entity.id:
                other = id_to_title.get(edge.source_entity_id)
                arrow = "←"
            else:
                continue
            if other is None:
                continue
            suffix = f" — {edge.label}" if edge.label else ""
            lines.append(f"- {edge.type} {arrow} [[{other}]]{suffix}")
        return lines

    def _render_image_markdown(self, src: str, alt: str) -> str:
        embed = self._files_url_to_embed(src)
        if embed is not None:
            return embed
        return f"![{alt}]({src})"

    def _files_url_to_embed(self, url: str) -> str | None:
        """Map an app attachment URL (/files/{entity_id}/{stored}) to the
        wiki-embed of the copy this exporter places in _attachments/."""
        if not self._config.export_attachments:
            return None
        match = _FILES_URL_RE.match(url)
        if match is None:
            return None
        name = f"{match.group('entity_id')}-{match.group('stored')}"
        return f"![[{name}]]"

    async def _write_note(
        self,
        entity: EntityOut,
        relpath: str,
        rendered: str,
        existing_links: dict[str, str],
    ) -> None:
        root = self._root
        target = root / relpath
        old_relpath = existing_links.get(entity.id)

        def write() -> None:
            if not Path(self._config.vault_path).is_dir():
                raise ConnectorUnavailableError(
                    self._context.connection_name,
                    f"vault path is not a directory: {self._config.vault_path}",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
            # The note moved (rename / type change): remove the stale file so
            # the vault doesn't accumulate duplicates.
            if old_relpath is not None and old_relpath != relpath:
                old_file = root / old_relpath
                if old_file.is_file():
                    old_file.unlink()

        await asyncio.to_thread(write)
        if self._config.export_attachments:
            await self._copy_attachments(entity)

    async def _copy_attachments(self, entity: EntityOut) -> None:
        attachments = await self._context.attachment_store.list_for_entity(entity.id)
        if not attachments:
            return
        target_dir = self._root / ATTACHMENTS_SUBFOLDER

        def copy_all() -> None:
            target_dir.mkdir(parents=True, exist_ok=True)
            for attachment in attachments:
                stored = attachment.url.rsplit("/", 1)[-1]
                source = self._context.attachments_dir / entity.id / stored
                if not source.is_file():
                    logger.warning("Attachment file missing on disk: %s", source)
                    continue
                (target_dir / f"{entity.id}-{stored}").write_bytes(source.read_bytes())

        await asyncio.to_thread(copy_all)

    def _attachment_embed(self, value: object) -> str | None:
        url = getattr(value, "url", None)
        if url is None and isinstance(value, dict):
            url = value.get("url")
        if not isinstance(url, str):
            return None
        return self._files_url_to_embed(url)

    # ── import ───────────────────────────────────────────────────────────────

    async def import_data(self, request: ImportRequest) -> ImportResult:
        del request  # Obsidian import has no payload: it reads the vault.
        root = self._root
        if not root.is_dir():
            raise ConnectorUnavailableError(
                self._context.connection_name,
                f"export folder not found in vault: {root}",
            )
        files = await asyncio.to_thread(
            lambda: sorted(
                p for p in root.rglob("*.md") if ATTACHMENTS_SUBFOLDER not in p.parts
            )
        )
        result = ImportResult()
        staged: list[_StagedNote] = []
        for file in files:
            relpath = file.relative_to(root).as_posix()
            try:
                text = await asyncio.to_thread(file.read_text, encoding="utf-8")
                staged.append(_parse_staged_note(text, relpath))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                result.errors.append(
                    ItemError(ref=relpath, code=error_code(e), detail=str(e))
                )

        # Pass 1: ensure every note has an entity (match by loregraph_id,
        # then by title, else create a bare one) so wikilinks between the
        # imported notes can resolve in pass 2.
        context = self._context
        existing = await context.entity_store.list_entities(context.project_id)
        title_to_id = {e.title.strip().lower(): e.id for e in existing}
        known_ids = {e.id for e in existing}
        for note in staged:
            try:
                entity_id = await self._match_or_create(note, title_to_id, known_ids)
                note.entity_id = entity_id
                title_to_id[note.title.strip().lower()] = entity_id
            except asyncio.CancelledError:
                raise
            except CampaignError as e:
                result.errors.append(
                    ItemError(ref=note.relpath, code=error_code(e), detail=str(e))
                )

        # Pass 2: full update with entityLink ids resolved (LWW).
        for note in staged:
            if note.entity_id is None:
                continue
            try:
                fields = note.build_fields(title_to_id)
                await context.entity_service.update(
                    context.project_id,
                    note.entity_id,
                    EntityUpdate(
                        type=note.entity_type, title=note.title, fields=fields
                    ),
                )
                if note.created:
                    result.created += 1
                else:
                    result.updated += 1
                await context.link_store.upsert(
                    context.connection_id,
                    note.entity_id,
                    note.relpath,
                    LINK_KIND_MD_FILE,
                )
            except asyncio.CancelledError:
                raise
            except CampaignError as e:
                result.errors.append(
                    ItemError(ref=note.relpath, code=error_code(e), detail=str(e))
                )

        # Pass 3: relationships (outgoing "→" lines only — the "←" mirror in
        # the target's note would create every edge twice).
        existing_edges = await context.edge_store.list_all(context.project_id)
        edge_keys = {
            (e.source_entity_id, e.target_entity_id, e.type) for e in existing_edges
        }
        for note in staged:
            if note.entity_id is None:
                continue
            for rel_type, target_title, label in note.outgoing_relationships:
                target_id = title_to_id.get(target_title.strip().lower())
                if target_id is None:
                    result.errors.append(
                        ItemError(
                            ref=note.relpath,
                            code="relationship_target_missing",
                            detail=f"[[{target_title}]] does not match any entity",
                        )
                    )
                    continue
                key = (note.entity_id, target_id, rel_type)
                if key in edge_keys:
                    result.skipped += 1
                    continue
                try:
                    await context.edge_service.create(
                        context.project_id,
                        EdgeCreate(
                            source_entity_id=note.entity_id,
                            target_entity_id=target_id,
                            type=rel_type,
                            label=label or None,
                        ),
                    )
                    edge_keys.add(key)
                except asyncio.CancelledError:
                    raise
                except CampaignError as e:
                    result.errors.append(
                        ItemError(ref=note.relpath, code=error_code(e), detail=str(e))
                    )
        return result

    async def _match_or_create(
        self,
        note: "_StagedNote",
        title_to_id: dict[str, str],
        known_ids: set[str],
    ) -> str:
        context = self._context
        if note.loregraph_id is not None and note.loregraph_id in known_ids:
            return note.loregraph_id
        matched = title_to_id.get(note.title.strip().lower())
        if matched is not None:
            return matched
        created = await context.entity_service.create(
            EntityCreate(type=note.entity_type, title=note.title, fields=[]),
            context.project_id,
        )
        note.created = True
        return created.id


class _ExportPlan:
    def __init__(
        self,
        items: list[tuple[EntityOut, str, str]],
        existing_links: dict[str, str],
    ) -> None:
        self.items = items
        self.existing_links = existing_links


class _StagedNote:
    def __init__(
        self,
        relpath: str,
        title: str,
        entity_type: str,
        loregraph_id: str | None,
        frontmatter_fields: list[EntityFieldIn],
        body_sections: list[tuple[str, str]],
        outgoing_relationships: list[tuple[str, str, str]],
    ) -> None:
        self.relpath = relpath
        self.title = title
        self.entity_type = entity_type
        self.loregraph_id = loregraph_id
        self.frontmatter_fields = frontmatter_fields
        self.body_sections = body_sections
        self.outgoing_relationships = outgoing_relationships
        self.entity_id: str | None = None
        self.created = False

    def build_fields(self, title_to_id: dict[str, str]) -> list[EntityFieldIn]:
        fields = list(self.frontmatter_fields)
        for key, markdown in self.body_sections:
            doc = markdown_to_prosemirror(markdown)
            resolve_entity_link_ids(doc, title_to_id)
            fields.append(
                EntityFieldIn(key=key, field_type=FieldType.RICH_TEXT, value=doc)
            )
        return fields


def _parse_staged_note(text: str, relpath: str) -> _StagedNote:
    frontmatter, body = parse_note(text, relpath)

    loregraph_id_raw = frontmatter.get("loregraph_id")
    loregraph_id = (
        loregraph_id_raw
        if isinstance(loregraph_id_raw, str) and loregraph_id_raw
        else None
    )
    entity_type_raw = frontmatter.get("type")
    entity_type = (
        entity_type_raw.strip()
        if isinstance(entity_type_raw, str) and entity_type_raw.strip()
        else "note"
    )

    fields: list[EntityFieldIn] = []
    tags: list[str] = []
    for key, value in frontmatter.items():
        if key in ("loregraph_id", "type"):
            continue
        if key == "tags":
            if isinstance(value, list):
                tags = [str(v) for v in value]
            continue
        if isinstance(value, bool):
            fields.append(
                EntityFieldIn(key=key, field_type=FieldType.TEXT, value=str(value))
            )
        elif isinstance(value, int | float):
            fields.append(
                EntityFieldIn(key=key, field_type=FieldType.NUMBER, value=value)
            )
        elif isinstance(value, str):
            fields.append(
                EntityFieldIn(key=key, field_type=FieldType.TEXT, value=value)
            )
        elif isinstance(value, list) and all(isinstance(v, str) for v in value):
            fields.append(EntityFieldIn(key=key, field_type=FieldType.TAG, value=value))
        # Other YAML shapes are dropped — nothing in the entity model fits.
    if tags:
        fields.append(EntityFieldIn(key="tags", field_type=FieldType.TAG, value=tags))

    title, sections, relationships = _split_body(body)
    if not title:
        stem = relpath.rsplit("/", 1)[-1].removesuffix(".md")
        title = stem
    if not title.strip():
        raise ExternalDataParseError(relpath, "note has no title")

    return _StagedNote(
        relpath=relpath,
        title=title.strip(),
        entity_type=entity_type,
        loregraph_id=loregraph_id,
        frontmatter_fields=fields,
        body_sections=sections,
        outgoing_relationships=relationships,
    )


def _split_body(
    body: str,
) -> tuple[str, list[tuple[str, str]], list[tuple[str, str, str]]]:
    """Split a note body into (H1 title, [(section key, markdown)], outgoing
    relationships). Preamble content before the first ``##`` (other than the
    H1 and the icon embed line) becomes a ``description`` section."""
    title = ""
    sections: list[tuple[str, str]] = []
    relationships: list[tuple[str, str, str]] = []
    current_key: str | None = None
    current_lines: list[str] = []
    preamble_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is None:
            return
        text = "\n".join(current_lines).strip()
        if current_key == RELATIONSHIPS_HEADING:
            for line in text.split("\n"):
                match = _RELATIONSHIP_LINE_RE.match(line.strip())
                if match is None or match.group("arrow") in ("←", "<-"):
                    continue
                relationships.append(
                    (
                        match.group("type"),
                        match.group("target"),
                        (match.group("label") or "").strip(),
                    )
                )
        elif text:
            sections.append((current_key, text))
        current_key = None
        current_lines = []

    for line in body.split("\n"):
        if line.startswith("## "):
            flush()
            current_key = line[3:].strip()
            current_lines = []
        elif line.startswith("# ") and not title:
            title = line[2:].strip()
        elif current_key is not None:
            current_lines.append(line)
        else:
            preamble_lines.append(line)
    flush()

    preamble = "\n".join(preamble_lines).strip()
    # Drop a leading icon embed (the exporter places one under the H1).
    preamble = re.sub(r"^!\[\[[^\]]+\]\]\s*", "", preamble).strip()
    if preamble:
        sections.insert(0, ("description", preamble))
    return title, sections, relationships


def _sanitize_filename(name: str) -> str:
    cleaned = _FILENAME_UNSAFE_RE.sub("", name).strip().rstrip(".")
    return re.sub(r"\s+", " ", cleaned)
