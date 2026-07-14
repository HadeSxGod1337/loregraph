import asyncio
import logging

from loregraph.services.document_ingest import chunk_text, extract_text
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.storage.protocols import KnowledgeSourceStore

logger = logging.getLogger(__name__)

# Truncated so a long traceback string never blows out the SQLite error column.
KB_ERROR_MESSAGE_MAX_CHARS = 500


async def ingest_source(
    source_id: str,
    project_id: str,
    content: bytes,
    content_type: str,
    filename: str,
    *,
    source_store: KnowledgeSourceStore,
    knowledge_index: KnowledgeIndex | None,
) -> None:
    """Background pipeline: extract text -> chunk -> index -> mark ready.

    Runs as a FastAPI BackgroundTask, scheduled after the upload response
    (status="pending") has already gone out — this function never raises
    into the request/response cycle; every outcome besides cancellation is
    reflected as a source status update instead.
    """
    try:
        await source_store.update_status(source_id, status="processing")
        if knowledge_index is None:
            # Embeddings disabled: the file is stored and listable, just not
            # searchable — the same degrade VectorIndex applies to canon.
            await source_store.update_status(source_id, status="ready", chunk_count=0)
            return
        # pypdf parsing and chunking are synchronous CPU/IO work — keep them
        # off the event loop so one large upload can't stall every other
        # request while it is being ingested (this runs as a BackgroundTask
        # on the same loop as live requests).
        text = await asyncio.to_thread(extract_text, content, content_type, filename)
        chunks = await asyncio.to_thread(chunk_text, text)
        await knowledge_index.index_source(project_id, source_id, chunks)
        await source_store.update_status(
            source_id, status="ready", chunk_count=len(chunks)
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(
            "Knowledge source ingestion failed for %s", source_id, exc_info=True
        )
        await source_store.update_status(
            source_id, status="failed", error=str(e)[:KB_ERROR_MESSAGE_MAX_CHARS]
        )
