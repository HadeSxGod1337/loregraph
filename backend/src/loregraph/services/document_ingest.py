"""Pure, LLM-free parsing/chunking for the project knowledge base.

Deterministic like XPBudgetCalculator (CLAUDE.md, "LLM для творчества, Python
для арифметики") — text extraction and chunk boundaries must be reproducible
and unit-testable without a model in the loop.
"""

import itertools
import re
from io import BytesIO
from pathlib import Path

import pypdf

from loregraph.exceptions import DocumentParsingError, UnsupportedDocumentTypeError

PDF_SUFFIX = ".pdf"
# Any format that's just UTF-8 text underneath, regardless of structure —
# decoding it doesn't care whether it's prose, JSON, or a CSV table. Shared
# with agent/multimodal.py (chat attachments) so "what counts as text" has
# one definition, not two allowlists that can drift apart.
TEXT_LIKE_SUFFIXES = frozenset(
    {".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".yaml", ".yml", ".log"}
)

# Chunk target size / overlap for the knowledge base's vector index — plain
# named constants, not literals inline (CLAUDE.md, "Без магии").
KB_CHUNK_MAX_CHARS = 1500
KB_CHUNK_OVERLAP = 200


def extract_text(content: bytes, content_type: str, filename: str) -> str:
    """Dispatches on the file extension: .pdf via pypdf, TEXT_LIKE_SUFFIXES
    (.txt/.md/.json/.csv/.yaml/...) as UTF-8.

    `content_type` is accepted (per the storage layer's upload contract) but
    the extension is authoritative — browsers/clients send unreliable MIME
    types for plain text, Markdown, YAML, etc.
    """
    del content_type  # extension-driven dispatch; kept for signature parity
    suffix = Path(filename).suffix.lower()
    if suffix == PDF_SUFFIX:
        return _extract_pdf_text(content, filename)
    if suffix in TEXT_LIKE_SUFFIXES:
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise DocumentParsingError(filename, str(e)) from e
    raise UnsupportedDocumentTypeError(filename)


def _extract_pdf_text(content: bytes, filename: str) -> str:
    try:
        reader = pypdf.PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as e:
        raise DocumentParsingError(filename, str(e)) from e
    return "\n\n".join(pages)


def chunk_text(
    text: str,
    *,
    max_chars: int = KB_CHUNK_MAX_CHARS,
    overlap: int = KB_CHUNK_OVERLAP,
) -> list[str]:
    """Splits text into overlapping chunks, preferring paragraph boundaries.

    Paragraphs (blank-line separated) are packed greedily up to `max_chars`;
    a paragraph longer than `max_chars` is hard-split. `overlap` chars from
    the tail of each chunk are repeated at the head of the next one so a
    retrieval hit near a boundary doesn't lose surrounding context.
    """
    normalized = text.strip()
    if not normalized:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
        else:
            units.extend(
                paragraph[i : i + max_chars]
                for i in range(0, len(paragraph), max_chars)
            )

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = unit
    if current:
        chunks.append(current)

    if overlap <= 0 or len(chunks) < 2:
        return chunks
    return [chunks[0]] + [
        f"{previous[-overlap:]}\n\n{chunk}"
        for previous, chunk in itertools.pairwise(chunks)
    ]
