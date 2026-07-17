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
#
# Sized against the default local embedder's real budget, not a round
# number: paraphrase-multilingual-MiniLM-L12-v2 (llm/embeddings.py) silently
# truncates its input to 128 tokens — anything past that is dropped before
# embedding, never an error. Measured empirically (fastembed 0.8, EN and RU
# prose alike) at ~3.8 chars/token, so the old 1500-char default only ever
# embedded its first ~480 chars; the rest, including this module's own
# overlap tail, was invisible to search. 350 chars stays under ~92 tokens,
# leaving headroom for tokenizer/script variance. embedding_provider=openai/
# cohere/etc. (config.Settings) have far larger real budgets, but this
# module stays model-agnostic by design (see module docstring) — chunk_text
# still accepts max_chars/overlap overrides for a caller that knows better.
KB_CHUNK_MAX_CHARS = 350
KB_CHUNK_OVERLAP = 60


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


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Hard-splits a single paragraph that alone exceeds max_chars.

    Cuts at the nearest earlier space so a piece never ends mid-word; falls
    back to a raw character cut only when the window has no space at all
    (e.g. one long unbroken token/URL), matching the old behavior for that
    case.
    """
    pieces: list[str] = []
    remaining = paragraph
    while len(remaining) > max_chars:
        cut = remaining.rfind(" ", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        pieces.append(remaining[:cut])
        remaining = remaining[cut:].lstrip(" ")
    if remaining:
        pieces.append(remaining)
    return pieces


def chunk_text(
    text: str,
    *,
    max_chars: int = KB_CHUNK_MAX_CHARS,
    overlap: int = KB_CHUNK_OVERLAP,
) -> list[str]:
    """Splits text into overlapping chunks, preferring paragraph boundaries.

    Paragraphs (blank-line separated) are packed greedily up to `max_chars`;
    a paragraph longer than `max_chars` is hard-split on word boundaries
    (see _split_long_paragraph). `overlap` chars from the tail of each chunk
    are repeated at the head of the next one so a retrieval hit near a
    boundary doesn't lose surrounding context.
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
            units.extend(_split_long_paragraph(paragraph, max_chars))

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
