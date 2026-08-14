import logging
from typing import Any

from loregraph.schemas.entity import EntityOut, FieldType
from loregraph.services.document_ingest import chunk_text
from loregraph.storage.protocols import EntityStore
from loregraph.storage.vectorstore.protocols import (
    LoreChunk,
    RetrievedChunk,
    VectorStore,
)

logger = logging.getLogger(__name__)

# Same budget and rationale as the knowledge base's KB_CHUNK_* (see
# services/document_ingest.py): sized against the default local embedder's
# real 128-token window, not a round number. Kept as separate constants
# because entity chunks also carry a repeated head line, and because a future
# change to one contour should not silently move the other.
ENTITY_CHUNK_MAX_CHARS = 350
ENTITY_CHUNK_OVERLAP = 60
# Floor for the body budget so an entity with an unusually long title still
# gets chunks with content in them rather than head-only slivers.
MIN_ENTITY_CHUNK_BODY_CHARS = 120


def _prosemirror_text(node: Any) -> str:
    """Flatten a ProseMirror JSON doc to plain text for embedding."""
    if isinstance(node, dict):
        # Extract entityLink labels so wikilinked names are searchable
        if node.get("type") == "entityLink":
            label = node.get("attrs", {}).get("label", "")
            return label if isinstance(label, str) else ""
        own = node.get("text")
        parts = [own] if isinstance(own, str) else []
        parts.extend(_prosemirror_text(child) for child in node.get("content", []))
        return " ".join(part for part in parts if part)
    if isinstance(node, list):
        return " ".join(_prosemirror_text(item) for item in node)
    return ""


def _entity_head(entity: EntityOut) -> str:
    return f"{entity.title} ({entity.type})"


def _entity_field_lines(entity: EntityOut) -> list[str]:
    lines: list[str] = []
    for field in entity.fields:
        match field.field_type:
            case FieldType.TEXT | FieldType.NUMBER:
                lines.append(f"{field.key}: {field.value}")
            case FieldType.BOOLEAN:
                # Was silently missing: a bool has no `case` arm and there was
                # no `case _` either, so "is_alive: false" never reached the
                # index at all. The explicit fallthrough below now makes the
                # next new FieldType a visible gap rather than another quiet one.
                lines.append(f"{field.key}: {field.value}")
            case FieldType.TAG:
                if isinstance(field.value, list):
                    lines.append(f"{field.key}: {', '.join(map(str, field.value))}")
            case FieldType.RICH_TEXT:
                text = _prosemirror_text(field.value)
                if text:
                    lines.append(f"{field.key}: {text}")
            case FieldType.ATTACHMENT:
                pass  # binary refs carry no semantic text
            case _:
                logger.warning(
                    "Field type %r has no vector-index representation; %s's "
                    "%r field is not searchable.",
                    field.field_type,
                    entity.id,
                    field.key,
                )
    return lines


def entity_to_text(entity: EntityOut) -> str:
    """Textual representation of an entity — for the vector index, for BM25,
    and for showing the entity back to the model in a tool result."""
    return "\n".join([_entity_head(entity), *_entity_field_lines(entity)])


def entity_chunk_texts(entity: EntityOut) -> list[str]:
    """The same content, cut to what an embedder will actually read.

    One vector per entity was silently lossy: the default local model
    (paraphrase-multilingual-MiniLM-L12-v2) truncates its input at 128 tokens
    — roughly 480 characters — so everything past the first few fields of a
    long character was dropped before embedding, with no error. The knowledge
    base already solved this (services/document_ingest.py, KB_CHUNK_*); this
    applies the same reasoning to entities.

    The head line is repeated on every chunk on purpose: a third slice of a
    biography that never names the character is unreachable by that
    character's name, which is worse than not chunking at all.
    """
    head = _entity_head(entity)
    lines = _entity_field_lines(entity)
    if not lines:
        return [head]
    budget = max(ENTITY_CHUNK_MAX_CHARS - len(head) - 1, MIN_ENTITY_CHUNK_BODY_CHARS)
    pieces = chunk_text(
        "\n\n".join(lines), max_chars=budget, overlap=ENTITY_CHUNK_OVERLAP
    )
    return [f"{head}\n{piece}" for piece in pieces] or [head]


def _chunks_for(entity: EntityOut) -> list[LoreChunk]:
    return [
        LoreChunk(entity_id=entity.id, text=text, chunk_index=index)
        for index, text in enumerate(entity_chunk_texts(entity))
    ]


class VectorIndex:
    """Keeps the vector store in sync with entity writes and serves queries.

    The index is derived data: every method degrades to a logged warning
    rather than failing the SQL write that triggered it — a stale index is
    repairable via reindex_project, a rolled-back user edit is not.
    """

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    async def index_entity(self, entity: EntityOut) -> None:
        await self._store.upsert(entity.project_id, _chunks_for(entity))

    async def remove_entity(self, project_id: str, entity_id: str) -> None:
        await self._store.delete(project_id, [entity_id])

    async def query(
        self, project_id: str, text: str, k: int = 5
    ) -> list[RetrievedChunk]:
        return await self._store.query(project_id, text, k=k)

    async def drop_project(self, project_id: str) -> None:
        await self._store.drop_project(project_id)

    async def reindex_project(self, entity_store: EntityStore, project_id: str) -> int:
        """Rebuild the whole collection from SQLite (the source of truth)."""
        await self._store.drop_project(project_id)
        entities = await entity_store.list_entities(project_id)
        await self._store.upsert(
            project_id, [chunk for entity in entities for chunk in _chunks_for(entity)]
        )
        # Entities, not chunks: this number is reported to the user as "how
        # much of my world got indexed", and chunk counts would make a
        # re-chunking look like the world had grown.
        return len(entities)
