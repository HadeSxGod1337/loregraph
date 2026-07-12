"""Builds LangChain v1 standard content blocks for one chat turn's files.

Verified against the pinned langchain-core==1.4.9 / langchain-anthropic==1.4.8 /
langchain-openai==1.3.4: `ImageContentBlock` ({"type": "image", "mime_type",
"base64"}), `FileContentBlock` ({"type": "file", ...}), and
`PlainTextContentBlock` ({"type": "text-plain", ...}) are auto-translated to
each provider's native request format by `is_data_content_block()` /
`_format_data_content_block()` inside both partner packages — no per-provider
branching needed here. This is deliberately NOT the project's knowledge base
(services/knowledge_index.py): these blocks live only inside one
HumanMessage's content, persisted by the LangGraph checkpointer along with
the rest of the conversation, never chunked or embedded.
"""

import base64
import binascii
from typing import Any

from loregraph.exceptions import UnsupportedAttachmentTypeError
from loregraph.schemas.agent import ChatAttachment

_PLAIN_TEXT_CONTENT_TYPES = {"text/plain", "text/markdown"}
_PDF_CONTENT_TYPE = "application/pdf"


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

    if attachment.content_type.startswith("image/"):
        return {
            "type": "image",
            "mime_type": attachment.content_type,
            "base64": attachment.data_base64,
        }
    if attachment.content_type == _PDF_CONTENT_TYPE:
        return {
            "type": "file",
            "mime_type": attachment.content_type,
            "base64": attachment.data_base64,
        }
    if attachment.content_type in _PLAIN_TEXT_CONTENT_TYPES:
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise UnsupportedAttachmentTypeError(
                attachment.filename, "not valid UTF-8 text"
            ) from e
        return {
            "type": "text-plain",
            "mime_type": "text/plain",
            "text": decoded,
            "title": attachment.filename,
        }
    raise UnsupportedAttachmentTypeError(attachment.filename, attachment.content_type)
