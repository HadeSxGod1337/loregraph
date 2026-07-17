"""ProseMirror (TipTap) JSON <-> Markdown codec.

The document node set is fixed by the frontend editor (see
frontend/src/components/entity/entityLink.tsx::buildRichTextExtensions):
StarterKit blocks/marks + Image + Underline + the custom ``entityLink`` node.
No maintained Python library understands that custom node, so the codec is
hand-rolled and snapshot/round-trip tested (tests/test_markdown_codec.py).

Anything unrecognized degrades to plain text — a lossy conversion must never
become a failed export/import.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


def _default_render_image(src: str, alt: str) -> str:
    return f"![{alt}]({src})"


@dataclass(frozen=True)
class MarkdownRenderOptions:
    """Hooks that let the caller (e.g. the Obsidian exporter) decide how
    entity links and images land in Markdown."""

    # (entity_id, stored_label) -> link text inside [[...]]. Default: the
    # stored label — callers with a live title map should resolve by id,
    # because stored labels go stale on rename (same rule as the UI chip).
    resolve_entity_link: Callable[[str, str], str] = lambda _id, label: label
    # (src, alt) -> full markdown for an image.
    render_image: Callable[[str, str], str] = _default_render_image


def prosemirror_to_markdown(
    doc: dict[str, Any], options: MarkdownRenderOptions | None = None
) -> str:
    options = options or MarkdownRenderOptions()
    blocks = [
        rendered
        for child in doc.get("content", [])
        if (rendered := _render_block(child, options)) is not None
    ]
    return "\n\n".join(block for block in blocks if block.strip())


def _render_block(node: dict[str, Any], options: MarkdownRenderOptions) -> str | None:
    node_type = node.get("type")
    match node_type:
        case "paragraph":
            return _render_inline(node.get("content", []), options)
        case "heading":
            level = int(node.get("attrs", {}).get("level", 1))
            level = min(max(level, 1), 6)
            return f"{'#' * level} {_render_inline(node.get('content', []), options)}"
        case "bulletList":
            return _render_list(node, options, ordered=False)
        case "orderedList":
            return _render_list(node, options, ordered=True)
        case "blockquote":
            inner_blocks = [
                rendered
                for child in node.get("content", [])
                if (rendered := _render_block(child, options)) is not None
            ]
            inner = "\n\n".join(inner_blocks)
            return "\n".join(f"> {line}" for line in inner.split("\n"))
        case "codeBlock":
            language = node.get("attrs", {}).get("language") or ""
            text = "".join(child.get("text", "") for child in node.get("content", []))
            return f"```{language}\n{text}\n```"
        case "horizontalRule":
            return "---"
        case "image":
            attrs = node.get("attrs", {})
            return options.render_image(
                str(attrs.get("src", "")), str(attrs.get("alt") or "")
            )
        case _:
            # Unknown block: salvage its inline text rather than dropping it.
            content = node.get("content")
            if isinstance(content, list):
                return _render_inline(content, options)
            return None


def _render_list(
    node: dict[str, Any],
    options: MarkdownRenderOptions,
    *,
    ordered: bool,
    indent: int = 0,
) -> str:
    lines: list[str] = []
    prefix_pad = "  " * indent
    for index, item in enumerate(node.get("content", []), start=1):
        marker = f"{index}." if ordered else "-"
        item_lines: list[str] = []
        for child in item.get("content", []):
            child_type = child.get("type")
            if child_type in ("bulletList", "orderedList"):
                item_lines.append(
                    _render_list(
                        child,
                        options,
                        ordered=child_type == "orderedList",
                        indent=indent + 1,
                    )
                )
            else:
                rendered = _render_block(child, options)
                if rendered:
                    item_lines.append(f"{prefix_pad}{marker} {rendered}")
                    marker = " " * len(marker)  # continuation lines align
        lines.extend(line for line in item_lines if line)
    return "\n".join(lines)


def _render_inline(
    content: list[dict[str, Any]], options: MarkdownRenderOptions
) -> str:
    parts: list[str] = []
    for node in content:
        node_type = node.get("type")
        if node_type == "text":
            parts.append(_apply_marks(node.get("text", ""), node.get("marks", [])))
        elif node_type == "entityLink":
            attrs = node.get("attrs", {})
            entity_id = str(attrs.get("entityId") or "")
            label = str(attrs.get("label") or "")
            parts.append(f"[[{options.resolve_entity_link(entity_id, label)}]]")
        elif node_type == "hardBreak":
            parts.append("  \n")
        elif node_type == "image":
            attrs = node.get("attrs", {})
            parts.append(
                options.render_image(
                    str(attrs.get("src", "")), str(attrs.get("alt") or "")
                )
            )
        elif isinstance(node.get("content"), list):
            parts.append(_render_inline(node["content"], options))
    return "".join(parts)


def _apply_marks(text: str, marks: list[dict[str, Any]]) -> str:
    if not text:
        return text
    for mark in marks:
        match mark.get("type"):
            case "code":
                text = f"`{text}`"
            case "bold":
                text = f"**{text}**"
            case "italic":
                text = f"*{text}*"
            case "strike":
                text = f"~~{text}~~"
            case "underline":
                # Markdown has no underline; Obsidian renders inline HTML.
                text = f"<u>{text}</u>"
            case "link":
                href = mark.get("attrs", {}).get("href", "")
                text = f"[{text}]({href})"
    return text


# ── Markdown -> ProseMirror ──────────────────────────────────────────────────

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_WIKI_EMBED_RE = re.compile(r"!\[\[([^\]]+)\]\]")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_UNDERLINE_RE = re.compile(r"<u>(.+?)</u>")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")


def markdown_to_prosemirror(markdown: str) -> dict[str, Any]:
    """Parse the Markdown subset this codec emits (plus common hand-written
    Obsidian constructs) into a ProseMirror doc. entityLink nodes come back
    with ``entityId=""`` — resolve them afterwards with
    :func:`resolve_entity_link_ids` once a title->id map exists."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    content: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.strip().startswith("```"):
            language = line.strip()[3:].strip()
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1  # closing fence
            node: dict[str, Any] = {"type": "codeBlock", "content": []}
            if language:
                node["attrs"] = {"language": language}
            if code_lines:
                node["content"] = [{"type": "text", "text": "\n".join(code_lines)}]
            content.append(node)
            continue
        if re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", line):
            content.append({"type": "horizontalRule"})
            index += 1
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            content.append(
                {
                    "type": "heading",
                    "attrs": {"level": len(heading.group(1))},
                    "content": _parse_inline(heading.group(2)),
                }
            )
            index += 1
            continue
        if line.lstrip().startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote_lines.append(lines[index].lstrip()[1:].lstrip())
                index += 1
            inner = markdown_to_prosemirror("\n".join(quote_lines))
            content.append({"type": "blockquote", "content": inner["content"]})
            continue
        if _BULLET_RE.match(line) or _ORDERED_RE.match(line):
            list_node, index = _parse_list(lines, index, indent=_line_indent(line))
            content.append(list_node)
            continue
        # Paragraph: consecutive non-empty, non-structural lines.
        para_lines: list[str] = []
        while (
            index < len(lines)
            and lines[index].strip()
            and not _HEADING_RE.match(lines[index])
            and not lines[index].lstrip().startswith(">")
            and not lines[index].strip().startswith("```")
            and not _BULLET_RE.match(lines[index])
            and not _ORDERED_RE.match(lines[index])
            and not re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", lines[index])
        ):
            para_lines.append(lines[index].rstrip())
            index += 1
        inline: list[dict[str, Any]] = []
        for line_index, para_line in enumerate(para_lines):
            if line_index > 0:
                inline.append({"type": "hardBreak"})
            inline.extend(_parse_inline(para_line))
        content.append({"type": "paragraph", "content": inline})
    if not content:
        content.append({"type": "paragraph", "content": []})
    return {"type": "doc", "content": content}


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_list(
    lines: list[str], start: int, *, indent: int
) -> tuple[dict[str, Any], int]:
    first = lines[start]
    ordered = bool(_ORDERED_RE.match(first))
    items: list[dict[str, Any]] = []
    index = start
    while index < len(lines):
        line = lines[index]
        match = _ORDERED_RE.match(line) if ordered else _BULLET_RE.match(line)
        other = _BULLET_RE.match(line) if ordered else _ORDERED_RE.match(line)
        if match and _line_indent(line) == indent:
            item_content: list[dict[str, Any]] = [
                {"type": "paragraph", "content": _parse_inline(match.group(2))}
            ]
            index += 1
            # Nested list directly below with deeper indentation?
            if index < len(lines):
                nested = _BULLET_RE.match(lines[index]) or _ORDERED_RE.match(
                    lines[index]
                )
                if nested and _line_indent(lines[index]) > indent:
                    nested_node, index = _parse_list(
                        lines, index, indent=_line_indent(lines[index])
                    )
                    item_content.append(nested_node)
            items.append({"type": "listItem", "content": item_content})
            continue
        if (match or other) and _line_indent(line) < indent:
            break  # parent list resumes
        if other and _line_indent(line) == indent:
            break  # list style changed at the same level -> new list
        break
    return (
        {"type": "orderedList" if ordered else "bulletList", "content": items},
        index,
    )


@dataclass(frozen=True)
class _InlinePattern:
    regex: re.Pattern[str]
    build: Callable[[re.Match[str]], list[dict[str, Any]]]


def _marked_text(match: re.Match[str], mark_type: str) -> list[dict[str, Any]]:
    inner = _parse_inline(match.group(1))
    for node in inner:
        if node.get("type") == "text":
            node.setdefault("marks", []).append({"type": mark_type})
    return inner


_INLINE_PATTERNS: list[_InlinePattern] = [
    _InlinePattern(
        _CODE_RE,
        lambda m: [{"type": "text", "text": m.group(1), "marks": [{"type": "code"}]}],
    ),
    _InlinePattern(
        _WIKI_EMBED_RE,
        # Obsidian image embed ![[file]] -> image node with a vault-relative src.
        lambda m: [{"type": "image", "attrs": {"src": m.group(1), "alt": ""}}],
    ),
    _InlinePattern(
        _IMAGE_RE,
        lambda m: [{"type": "image", "attrs": {"src": m.group(2), "alt": m.group(1)}}],
    ),
    _InlinePattern(
        _WIKILINK_RE,
        lambda m: [
            {
                "type": "entityLink",
                "attrs": {"entityId": "", "fieldKey": None, "label": m.group(1)},
            }
        ],
    ),
    _InlinePattern(
        _LINK_RE,
        lambda m: [
            {
                "type": "text",
                "text": m.group(1),
                "marks": [{"type": "link", "attrs": {"href": m.group(2)}}],
            }
        ],
    ),
    _InlinePattern(_BOLD_RE, lambda m: _marked_text(m, "bold")),
    _InlinePattern(_STRIKE_RE, lambda m: _marked_text(m, "strike")),
    _InlinePattern(_UNDERLINE_RE, lambda m: _marked_text(m, "underline")),
    _InlinePattern(_ITALIC_RE, lambda m: _marked_text(m, "italic")),
]


def _parse_inline(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    # Find the earliest match among all patterns; recurse on both sides.
    best: tuple[int, re.Match[str], _InlinePattern] | None = None
    for pattern in _INLINE_PATTERNS:
        match = pattern.regex.search(text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), match, pattern)
    if best is None:
        return [{"type": "text", "text": text}]
    _, match, pattern = best
    nodes: list[dict[str, Any]] = []
    if match.start() > 0:
        nodes.extend(_parse_inline(text[: match.start()]))
    nodes.extend(pattern.build(match))
    if match.end() < len(text):
        nodes.extend(_parse_inline(text[match.end() :]))
    return nodes


def resolve_entity_link_ids(node: object, title_to_id: dict[str, str]) -> None:
    """Second import pass: fill in entityLink ids from a case-insensitive
    title->id map. Unresolved links keep entityId="" — the UI renders them
    as broken links rather than guessing (same rule as project_transfer)."""
    if isinstance(node, dict):
        attrs = node.get("attrs")
        if node.get("type") == "entityLink" and isinstance(attrs, dict):
            label = attrs.get("label")
            if isinstance(label, str) and not attrs.get("entityId"):
                attrs["entityId"] = title_to_id.get(label.lower(), "")
        for child in node.get("content", []):
            resolve_entity_link_ids(child, title_to_id)
    elif isinstance(node, list):
        for item in node:
            resolve_entity_link_ids(item, title_to_id)
