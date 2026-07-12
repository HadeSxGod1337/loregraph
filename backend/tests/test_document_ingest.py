import itertools

import pytest

from loregraph.exceptions import DocumentParsingError, UnsupportedDocumentTypeError
from loregraph.services.document_ingest import chunk_text, extract_text


def _make_test_pdf(text: str) -> bytes:
    """A hand-built single-page PDF with one text run — pypdf can't author
    PDFs (only read/manipulate), and pulling in a generator library just for
    this test isn't worth it. pypdf recovers from the deliberately-wrong
    startxref offset via its full-scan fallback (verified empirically)."""
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode()
    return (
        f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> \
/MediaBox [0 0 200 100] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length {len(stream)} >>
stream
{stream.decode()}
endstream
endobj
trailer
<< /Size 6 /Root 1 0 R >>
startxref
0
%%EOF
"""
    ).encode()


def test_extract_text_from_pdf() -> None:
    pdf_bytes = _make_test_pdf("Hello Knowledge Base")
    text = extract_text(pdf_bytes, "application/pdf", "rulebook.pdf")
    assert "Hello Knowledge Base" in text


def test_extract_text_from_plain_text() -> None:
    text = extract_text(b"Some setting notes.", "text/plain", "setting.txt")
    assert text == "Some setting notes."


def test_extract_text_from_markdown() -> None:
    text = extract_text(b"# Title\n\nBody.", "text/markdown", "notes.md")
    assert text == "# Title\n\nBody."


def test_extract_text_from_json() -> None:
    text = extract_text(b'{"faction": "Order of the Gauntlet"}', "", "setting.json")
    assert "Order of the Gauntlet" in text


def test_extract_text_from_csv() -> None:
    text = extract_text(b"name,role\nMira,smith", "", "npcs.csv")
    assert "Mira,smith" in text


def test_extract_text_from_yaml() -> None:
    text = extract_text(b"faction: Order of the Gauntlet", "", "notes.yaml")
    assert "Order of the Gauntlet" in text


def test_extract_text_content_type_is_ignored_for_dispatch() -> None:
    """The extension is authoritative — browsers send unreliable MIME types
    for .json/.yaml/etc (often application/octet-stream)."""
    text = extract_text(b"a: b", "application/octet-stream", "notes.yml")
    assert text == "a: b"


def test_extract_text_unsupported_extension_raises() -> None:
    with pytest.raises(UnsupportedDocumentTypeError):
        extract_text(b"binary", "image/png", "art.png")


def test_extract_text_invalid_utf8_raises_parsing_error() -> None:
    with pytest.raises(DocumentParsingError):
        extract_text(b"\xff\xfe\x00bad", "text/plain", "broken.txt")


def test_chunk_text_empty_input_returns_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_short_text_is_one_chunk() -> None:
    chunks = chunk_text("A single short paragraph.", max_chars=1500, overlap=200)
    assert chunks == ["A single short paragraph."]


def test_chunk_text_packs_paragraphs_up_to_max_chars() -> None:
    paragraphs = [f"Paragraph {i}." for i in range(20)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=60, overlap=0)
    assert len(chunks) > 1
    assert all(len(chunk) <= 60 for chunk in chunks)
    # every paragraph shows up somewhere in the reassembled chunks
    assert all(any(p in chunk for chunk in chunks) for p in paragraphs)


def test_chunk_text_hard_splits_a_paragraph_longer_than_max_chars() -> None:
    long_paragraph = "x" * 500
    chunks = chunk_text(long_paragraph, max_chars=100, overlap=0)
    assert len(chunks) >= 5
    assert all(len(chunk) <= 100 for chunk in chunks)


def test_chunk_text_overlap_repeats_tail_of_previous_chunk() -> None:
    paragraphs = [
        f"Paragraph {i} with some extra text to pad it out." for i in range(6)
    ]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=80, overlap=20)
    assert len(chunks) > 1
    for previous, chunk in itertools.pairwise(chunks):
        assert previous[-20:] in chunk
