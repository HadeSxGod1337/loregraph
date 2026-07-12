import base64

import pytest

from loregraph.agent.multimodal import build_message_content
from loregraph.exceptions import UnsupportedAttachmentTypeError
from loregraph.schemas.agent import ChatAttachment


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def test_no_attachments_returns_plain_string() -> None:
    assert build_message_content("Hello", []) == "Hello"


def test_image_attachment_becomes_image_block() -> None:
    content = build_message_content(
        "What is this?",
        [
            ChatAttachment(
                filename="a.png",
                content_type="image/png",
                data_base64=_b64(b"png-bytes"),
            )
        ],
    )
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "What is this?"}
    assert content[1] == {
        "type": "image",
        "mime_type": "image/png",
        "base64": _b64(b"png-bytes"),
    }


def test_pdf_attachment_becomes_file_block() -> None:
    content = build_message_content(
        "Summarize this",
        [
            ChatAttachment(
                filename="rules.pdf",
                content_type="application/pdf",
                data_base64=_b64(b"pdf-bytes"),
            )
        ],
    )
    assert isinstance(content, list)
    assert content[1] == {
        "type": "file",
        "mime_type": "application/pdf",
        "base64": _b64(b"pdf-bytes"),
    }


def test_plain_text_attachment_becomes_text_plain_block() -> None:
    content = build_message_content(
        "See notes",
        [
            ChatAttachment(
                filename="notes.txt",
                content_type="text/plain",
                data_base64=_b64("Привет мир".encode()),
            )
        ],
    )
    assert isinstance(content, list)
    assert content[1] == {
        "type": "text-plain",
        "mime_type": "text/plain",
        "text": "Привет мир",
        "title": "notes.txt",
    }


def test_markdown_attachment_becomes_text_plain_block() -> None:
    content = build_message_content(
        "See notes",
        [
            ChatAttachment(
                filename="notes.md",
                content_type="text/markdown",
                data_base64=_b64(b"# Title"),
            )
        ],
    )
    assert isinstance(content, list)
    block = content[1]
    assert isinstance(block, dict)
    assert block["type"] == "text-plain"
    assert block["text"] == "# Title"


def test_json_attachment_becomes_text_plain_block() -> None:
    content = build_message_content(
        "What's in this?",
        [
            ChatAttachment(
                filename="party.json",
                content_type="application/json",
                data_base64=_b64(b'{"name": "Mira"}'),
            )
        ],
    )
    assert isinstance(content, list)
    block = content[1]
    assert isinstance(block, dict)
    assert block["type"] == "text-plain"
    assert block["text"] == '{"name": "Mira"}'


def test_pdf_detected_by_extension_even_with_generic_content_type() -> None:
    """Browsers sometimes report application/octet-stream for a .pdf pick —
    the extension must still resolve it to a file block."""
    content = build_message_content(
        "Summarize",
        [
            ChatAttachment(
                filename="rules.pdf",
                content_type="application/octet-stream",
                data_base64=_b64(b"pdf-bytes"),
            )
        ],
    )
    assert isinstance(content, list)
    block = content[1]
    assert isinstance(block, dict)
    assert block["type"] == "file"
    assert block["mime_type"] == "application/pdf"


def test_unsupported_image_mime_type_raises() -> None:
    """jpeg/png/gif/webp only — anything else would otherwise pass this
    check and only fail once it reaches the LLM provider."""
    with pytest.raises(UnsupportedAttachmentTypeError):
        build_message_content(
            "x",
            [
                ChatAttachment(
                    filename="scan.bmp",
                    content_type="image/bmp",
                    data_base64=_b64(b"x"),
                )
            ],
        )


def test_multiple_attachments_produce_multiple_blocks() -> None:
    content = build_message_content(
        "Two files",
        [
            ChatAttachment(
                filename="a.png", content_type="image/png", data_base64=_b64(b"x")
            ),
            ChatAttachment(
                filename="b.pdf",
                content_type="application/pdf",
                data_base64=_b64(b"y"),
            ),
        ],
    )
    assert isinstance(content, list)
    assert len(content) == 3  # text + image + file


def test_unsupported_content_type_raises() -> None:
    with pytest.raises(UnsupportedAttachmentTypeError):
        build_message_content(
            "x",
            [
                ChatAttachment(
                    filename="video.mp4",
                    content_type="video/mp4",
                    data_base64=_b64(b"x"),
                )
            ],
        )


def test_invalid_base64_raises() -> None:
    with pytest.raises(UnsupportedAttachmentTypeError):
        build_message_content(
            "x",
            [
                ChatAttachment(
                    filename="a.png",
                    content_type="image/png",
                    data_base64="not-base64!!",
                )
            ],
        )


def test_non_utf8_plain_text_raises() -> None:
    with pytest.raises(UnsupportedAttachmentTypeError):
        build_message_content(
            "x",
            [
                ChatAttachment(
                    filename="a.txt",
                    content_type="text/plain",
                    data_base64=_b64(b"\xff\xfe\x00bad"),
                )
            ],
        )
