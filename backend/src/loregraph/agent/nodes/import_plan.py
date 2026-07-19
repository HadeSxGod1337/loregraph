import asyncio
from typing import Any

from loregraph.agent.import_state import ImportState, WindowSpec
from loregraph.services.document_ingest import chunk_text, extract_text
from loregraph.storage.protocols import KnowledgeSourceStore

# Windows for LORE EXTRACTION, not the KB's own embedding-sized chunks
# (KB_CHUNK_MAX_CHARS=350 in document_ingest.py — sized for a 128-token
# local embedder). A window here is what one extraction LLM call reads —
# much bigger, so a window is a few paragraphs of real narrative, not a
# fragment. chunk_text is reused as-is: it's already a generic, paragraph-
# aware packer/splitter, just called with different constants.
IMPORT_WINDOW_MAX_CHARS = 20_000
IMPORT_WINDOW_OVERLAP_CHARS = 500


async def plan_windows(
    state: ImportState, *, source_store: KnowledgeSourceStore
) -> dict[str, Any]:
    """First node: re-derive the document's full text from the stored
    upload bytes (not the KB's chunked/embedded copy) and slice it into
    extraction-sized windows. Pure/deterministic — no LLM call."""
    source = await source_store.get(state.source_id)
    content = await source_store.read_content(state.source_id)
    text = await asyncio.to_thread(
        extract_text, content, source.content_type, source.original_filename
    )
    window_texts = await asyncio.to_thread(
        chunk_text,
        text,
        max_chars=IMPORT_WINDOW_MAX_CHARS,
        overlap=IMPORT_WINDOW_OVERLAP_CHARS,
    )
    windows = [
        WindowSpec(index=i, text=window_text)
        for i, window_text in enumerate(window_texts)
    ]
    return {"windows": windows}
