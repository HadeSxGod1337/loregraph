import logging
from typing import Any

from loregraph.schemas.entity import EntityOut, FieldType
from loregraph.storage.protocols import EntityStore
from loregraph.storage.vectorstore.protocols import (
    LoreChunk,
    RetrievedChunk,
    VectorStore,
)

logger = logging.getLogger(__name__)


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


def entity_to_text(entity: EntityOut) -> str:
    """Textual representation of an entity for the vector index."""
    parts = [f"{entity.title} ({entity.type})"]
    for field in entity.fields:
        match field.field_type:
            case FieldType.TEXT | FieldType.NUMBER:
                parts.append(f"{field.key}: {field.value}")
            case FieldType.TAG:
                if isinstance(field.value, list):
                    parts.append(f"{field.key}: {', '.join(map(str, field.value))}")
            case FieldType.RICH_TEXT:
                text = _prosemirror_text(field.value)
                if text:
                    parts.append(f"{field.key}: {text}")
            case FieldType.ATTACHMENT:
                pass  # binary refs carry no semantic text
    return "\n".join(parts)


class VectorIndex:
    """Keeps the vector store in sync with entity writes and serves queries.

    The index is derived data: every method degrades to a logged warning
    rather than failing the SQL write that triggered it — a stale index is
    repairable via reindex_project, a rolled-back user edit is not.
    """

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    async def index_entity(self, entity: EntityOut) -> None:
        chunk = LoreChunk(entity_id=entity.id, text=entity_to_text(entity))
        await self._store.upsert(entity.project_id, [chunk])

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
        chunks = [
            LoreChunk(entity_id=entity.id, text=entity_to_text(entity))
            for entity in entities
        ]
        await self._store.upsert(project_id, chunks)
        return len(chunks)
