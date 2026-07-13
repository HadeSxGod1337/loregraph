"""Builds LangChain v1 standard content blocks for one chat turn's files.

Verified against the pinned langchain-core==1.4.9 / langchain-anthropic==1.4.8 /
langchain-openai==1.3.4: `ImageContentBlock` ({"type": "image", "mime_type",
"base64"}) and `FileContentBlock` ({"type": "file", ...}) are auto-translated
to each provider's native request format by `is_data_content_block()` /
`_format_data_content_block()` inside both partner packages — no per-provider
branching needed for those two.

`PlainTextContentBlock` ({"type": "text-plain", ...}) is NOT one of them:
langchain-anthropic implements it, but langchain_openai's
convert_to_openai_data_block only handles "image"/"file"/"audio" and raises
ValueError on anything else — confirmed against the installed package, not
assumed. Rather than special-case providers here, text-like attachments
(.txt/.md/.json/.csv/.yaml/...) are inlined as plain `{"type": "text"}`
blocks instead — that block type needs no provider-specific translation at
all, since it's just more text in the same message.

This is deliberately NOT the project's knowledge base (services/
knowledge_index.py): these blocks live only inside one HumanMessage's
content, persisted by the LangGraph checkpointer along with the rest of the
conversation, never chunked or embedded.
"""

import base64
import binascii
from pathlib import Path
from typing import Any

from loregraph.exceptions import UnsupportedAttachmentTypeError
from loregraph.schemas.agent import ChatAttachment
from loregraph.services.document_ingest import PDF_SUFFIX, TEXT_LIKE_SUFFIXES

_PDF_CONTENT_TYPE = "application/pdf"
# What Claude and GPT-4/5 vision actually decode — not "image/*". Anything
# else (bmp, tiff, svg, heic...) would otherwise pass our check and only
# fail once it reaches the provider, as a much uglier error.
_SUPPORTED_IMAGE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp"}
)
# A text-like attachment is inlined straight into the prompt (see module
# docstring) — unlike a binary file, its size counts directly against the
# model's context/token budget, so it gets its own, much smaller cap than
# MAX_CHAT_ATTACHMENT_BYTES (which just bounds the upload itself). Truncated
# rather than rejected, matching this codebase's existing "shorten with a
# marker" convention for prompt-bound text (see agent/nodes/tools.py's
# DETAIL_TEXT_LIMIT).
MAX_INLINE_TEXT_CHARS = 20_000


def build_message_content(
    text: str, attachments: list[ChatAttachment]
) -> str | list[str | dict[Any, Any]]:
    """A plain string when there are no attachments (unchanged current
    behavior/wire format), otherwise a list of content blocks.

    Return type matches langchain_core.messages.HumanMessage's `content`
    parameter exactly (str | list[str | dict[Any, Any]]) so callers can pass
    the result straight through without a cast."""
    if not attachments:
        return text
    blocks: list[str | dict[Any, Any]] = [{"type": "text", "text": text}]
    for attachment in attachments:
        blocks.append(_attachment_block(attachment))
    return blocks


def _attachment_block(attachment: ChatAttachment) -> dict[str, Any]:
    try:
        raw = base64.b64decode(attachment.data_base64, validate=True)
    except binascii.Error as e:
        raise UnsupportedAttachmentTypeError(
            attachment.filename, "invalid base64 data"
        ) from e

    # Images are only reliably identifiable by content_type (browsers sniff
    # these correctly); text-like files and PDFs go by extension, same
    # extension-is-authoritative reasoning as document_ingest.extract_text —
    # browsers routinely mislabel .json/.yaml/.md as application/octet-stream.
    if attachment.content_type in _SUPPORTED_IMAGE_MIME_TYPES:
        return {
            "type": "image",
            "mime_type": attachment.content_type,
            "base64": attachment.data_base64,
        }
    if attachment.content_type.startswith("image/"):
        raise UnsupportedAttachmentTypeError(
            attachment.filename,
            f"image type {attachment.content_type!r} isn't supported by the "
            "configured LLM provider (jpeg, png, gif, webp only)",
        )

    suffix = Path(attachment.filename).suffix.lower()
    if suffix == PDF_SUFFIX or attachment.content_type == _PDF_CONTENT_TYPE:
        return {
            "type": "file",
            "mime_type": _PDF_CONTENT_TYPE,
            "base64": attachment.data_base64,
            # langchain_openai warns and substitutes a placeholder filename
            # when this is missing; harmless extra key for Anthropic, which
            # only reads mime_type/base64 off a "file" block.
            "filename": attachment.filename,
        }
    if suffix in TEXT_LIKE_SUFFIXES:
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise UnsupportedAttachmentTypeError(
                attachment.filename, "not valid UTF-8 text"
            ) from e
        if len(decoded) > MAX_INLINE_TEXT_CHARS:
            decoded = decoded[:MAX_INLINE_TEXT_CHARS] + "\n…(truncated)"
        return {
            "type": "text",
            "text": f'<attached_file name="{attachment.filename}">\n'
            f"{decoded}\n</attached_file>",
        }
    raise UnsupportedAttachmentTypeError(attachment.filename, attachment.content_type)
