import asyncio
from typing import Any

from loregraph.agent.import_source import ImportSourceResolver
from loregraph.agent.import_state import ImportState, WindowSpec
from loregraph.services.document_ingest import chunk_text

# Windows for LORE EXTRACTION, not the KB's own embedding-sized chunks
# (KB_CHUNK_MAX_CHARS=350 in document_ingest.py — sized for a 128-token
# local embedder). A window here is what one extraction LLM call reads —
# much bigger, so a window is a few paragraphs of real narrative, not a
# fragment. chunk_text is reused as-is: it's already a generic, paragraph-
# aware packer/splitter, just called with different constants.
IMPORT_WINDOW_MAX_CHARS = 20_000
IMPORT_WINDOW_OVERLAP_CHARS = 500


async def plan_windows(
    state: ImportState, *, source_resolver: ImportSourceResolver
) -> dict[str, Any]:
    """First node: resolve the source to plain-text documents (an uploaded
    file, or a connection's own content when migrating an external project —
    see agent/import_source.py) and slice it into extraction-sized windows.
    Pure/deterministic — no LLM call.

    Multiple documents are concatenated under `# title` headers and windowed
    as one stream rather than windowed individually: a migrated vault can
    hold hundreds of short notes, and one window (= one extraction call) per
    note would multiply cost for no gain. chunk_text packs them efficiently
    and the headers keep each document's boundary explicit to the extractor.
    A single document (the file-import path) is windowed exactly as before,
    with no header added."""
    documents = await source_resolver.load_documents(
        state.source_kind, state.source_id, state.project_id
    )
    if len(documents) == 1:
        combined = documents[0].text
    else:
        combined = "\n\n".join(f"# {doc.title}\n\n{doc.text}" for doc in documents)
    window_texts = await asyncio.to_thread(
        chunk_text,
        combined,
        max_chars=IMPORT_WINDOW_MAX_CHARS,
        overlap=IMPORT_WINDOW_OVERLAP_CHARS,
    )
    windows = [
        WindowSpec(index=i, text=window_text)
        for i, window_text in enumerate(window_texts)
    ]
    return {"windows": windows}
