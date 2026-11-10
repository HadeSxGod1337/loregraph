import logging

from loregraph.storage.vectorstore.protocols import (
    LoreChunk,
    RetrievedChunk,
    VectorStore,
)

# Retrieval fan-out for retrieve_context's knowledge_base query (see
# agent/nodes/retrieve_context.py) — separate constant from the lore
# RETRIEVAL_K since the two contours are independent.
KB_RETRIEVAL_K = 4


def log_retrieval(
    logger: logging.Logger,
    *,
    project_id: str,
    knowledge_index: "KnowledgeIndex | None",
    chunks: list[RetrievedChunk],
) -> None:
    """Diagnostics for a KB query outcome, callable from any node that queries
    a KnowledgeIndex (retrieve_context, the assistant's search_knowledge_base
    tool, brainstorm). "Nothing relevant" and "the index isn't even
    configured" both collapse to the same NO_KNOWLEDGE_SENTINEL text in the
    prompt — deliberately, so the model reads either one as "keep inventing",
    never as evidence the upload doesn't exist — which means the only place
    left to tell them apart is here. Takes the caller's own logger so the
    record's logger name still identifies which node ran the query. Never
    logs chunk text: campaign lore is often private."""
    if knowledge_index is None:
        logger.debug(
            "kb_retrieval project_id=%s available=false attempted=false "
            "reason=embeddings_disabled",
            project_id,
        )
        return
    logger.debug(
        "kb_retrieval project_id=%s available=true attempted=true hits=%d",
        project_id,
        len(chunks),
    )


def _kb_namespace(project_id: str) -> str:
    """Reference documents live in their own Chroma collection, isolated from
    the world-canon collection (`p_{project_id}`, VectorIndex) — same
    project, different namespace, so ChromaVectorStore._collection_sync
    builds a distinct collection with zero changes to it or to VectorStore."""
    return f"kb_{project_id}"


class KnowledgeIndex:
    """Vector index over a project's uploaded reference documents.

    Shaped identically to VectorIndex but reused over the *same*
    ChromaVectorStore instance via a different namespace — DIP means this
    class never touches Chroma directly, only the shared VectorStore Protocol.
    Derived data: callers are expected to log-and-degrade on failure, this
    class does not swallow errors itself (see services/knowledge_ingest.py).
    """

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    async def index_source(
        self, project_id: str, source_id: str, chunks: list[str]
    ) -> None:
        lore_chunks = [
            LoreChunk(entity_id=f"{source_id}:{i}", text=chunk)
            for i, chunk in enumerate(chunks)
        ]
        await self._store.upsert(_kb_namespace(project_id), lore_chunks)

    async def remove_source(
        self, project_id: str, source_id: str, chunk_count: int
    ) -> None:
        ids = [f"{source_id}:{i}" for i in range(chunk_count)]
        await self._store.delete(_kb_namespace(project_id), ids)

    async def query(
        self, project_id: str, text: str, k: int = KB_RETRIEVAL_K
    ) -> list[RetrievedChunk]:
        return await self._store.query(_kb_namespace(project_id), text, k=k)

    async def drop_project(self, project_id: str) -> None:
        await self._store.drop_project(_kb_namespace(project_id))
