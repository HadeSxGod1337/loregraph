from typing import Any

from loregraph.connectors.markdown_codec import (
    MarkdownRenderOptions,
    markdown_to_prosemirror,
    prosemirror_to_markdown,
    resolve_entity_link_ids,
)


def _doc(*content: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "content": list(content)}


def _para(*inline: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(inline)}


def _text(text: str, *marks: str) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = [{"type": mark} for mark in marks]
    return node


def test_snapshot_full_document() -> None:
    doc = _doc(
        {"type": "heading", "attrs": {"level": 2}, "content": [_text("The Forge")]},
        _para(
            _text("Run by "),
            {
                "type": "entityLink",
                "attrs": {"entityId": "abc", "fieldKey": None, "label": "Old Name"},
            },
            _text(" in the "),
            _text("lower city", "bold"),
            _text("."),
        ),
        {
            "type": "bulletList",
            "content": [
                {"type": "listItem", "content": [_para(_text("swords"))]},
                {"type": "listItem", "content": [_para(_text("armor", "italic"))]},
            ],
        },
        {"type": "blockquote", "content": [_para(_text("Iron remembers."))]},
        {
            "type": "codeBlock",
            "attrs": {"language": "txt"},
            "content": [{"type": "text", "text": "DC 15"}],
        },
        {"type": "horizontalRule"},
    )
    options = MarkdownRenderOptions(
        resolve_entity_link=lambda entity_id, label: (
            "Mira Kuznetz" if entity_id == "abc" else label
        )
    )
    markdown = prosemirror_to_markdown(doc, options)
    assert markdown == (
        "## The Forge\n\n"
        "Run by [[Mira Kuznetz]] in the **lower city**.\n\n"
        "- swords\n"
        "- *armor*\n\n"
        "> Iron remembers.\n\n"
        "```txt\nDC 15\n```\n\n"
        "---"
    )


def test_stale_entity_link_label_resolved_by_id() -> None:
    doc = _doc(
        _para(
            {
                "type": "entityLink",
                "attrs": {"entityId": "e1", "fieldKey": None, "label": "Stale"},
            }
        )
    )
    options = MarkdownRenderOptions(
        resolve_entity_link=lambda entity_id, label: "Fresh Title"
    )
    assert prosemirror_to_markdown(doc, options) == "[[Fresh Title]]"


def test_unknown_block_degrades_to_inline_text() -> None:
    doc = _doc({"type": "mysteryBlock", "content": [_text("salvaged")]})
    assert prosemirror_to_markdown(doc) == "salvaged"


def test_roundtrip_preserves_structure_and_marks() -> None:
    original = _doc(
        {"type": "heading", "attrs": {"level": 3}, "content": [_text("Secrets")]},
        _para(
            _text("Knows about "),
            {
                "type": "entityLink",
                "attrs": {"entityId": "", "fieldKey": None, "label": "The Vault"},
            },
            _text(" and "),
            _text("fears it", "bold"),
            _text("."),
        ),
        {
            "type": "orderedList",
            "content": [
                {"type": "listItem", "content": [_para(_text("first"))]},
                {"type": "listItem", "content": [_para(_text("second"))]},
            ],
        },
    )
    roundtripped = markdown_to_prosemirror(prosemirror_to_markdown(original))
    assert roundtripped == original


def test_markdown_to_prosemirror_parses_wikilinks_and_images() -> None:
    doc = markdown_to_prosemirror("See [[Mira]] and ![[icon.png]] here.")
    inline = doc["content"][0]["content"]
    types = [node["type"] for node in inline]
    assert "entityLink" in types
    assert "image" in types
    link = next(node for node in inline if node["type"] == "entityLink")
    assert link["attrs"] == {"entityId": "", "fieldKey": None, "label": "Mira"}


def test_resolve_entity_link_ids_fills_known_titles_only() -> None:
    doc = markdown_to_prosemirror("[[Known]] and [[Unknown]]")
    resolve_entity_link_ids(doc, {"known": "id-1"})
    links = [
        node for node in doc["content"][0]["content"] if node["type"] == "entityLink"
    ]
    assert links[0]["attrs"]["entityId"] == "id-1"
    # Unresolved stays empty — rendered as a broken link, never guessed.
    assert links[1]["attrs"]["entityId"] == ""


def test_nested_bullet_list_roundtrip() -> None:
    markdown = "- parent\n  - child"
    doc = markdown_to_prosemirror(markdown)
    assert prosemirror_to_markdown(doc) == markdown


def test_task_list_roundtrip_keeps_checked_state() -> None:
    markdown = "- [ ] scout the pass\n- [x] bribe the guard"
    doc = markdown_to_prosemirror(markdown)
    task_list = doc["content"][0]
    assert task_list["type"] == "taskList"
    assert [item["attrs"]["checked"] for item in task_list["content"]] == [False, True]
    assert prosemirror_to_markdown(doc) == markdown


def test_table_renders_as_gfm_and_roundtrips() -> None:
    doc = _doc(
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableHeader", "content": [_para(_text("Monster"))]},
                        {"type": "tableHeader", "content": [_para(_text("CR"))]},
                    ],
                },
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableCell", "content": [_para(_text("Goblin"))]},
                        {"type": "tableCell", "content": [_para(_text("1/4"))]},
                    ],
                },
            ],
        }
    )
    markdown = prosemirror_to_markdown(doc)
    assert markdown == ("| Monster | CR |\n| --- | --- |\n| Goblin | 1/4 |")
    assert prosemirror_to_markdown(markdown_to_prosemirror(markdown)) == markdown


def test_pipe_row_without_delimiter_stays_a_paragraph() -> None:
    doc = markdown_to_prosemirror("| not | a table |")
    assert doc["content"][0]["type"] == "paragraph"


def test_highlight_mark_roundtrip() -> None:
    doc = markdown_to_prosemirror("beware the ==ambush== here")
    marks = [
        mark["type"]
        for node in doc["content"][0]["content"]
        for mark in node.get("marks", [])
    ]
    assert marks == ["highlight"]
    assert prosemirror_to_markdown(doc) == "beware the ==ambush== here"


def test_hard_break_within_paragraph() -> None:
    doc = markdown_to_prosemirror("line one\nline two")
    inline = doc["content"][0]["content"]
    assert {"type": "hardBreak"} in inline
    assert prosemirror_to_markdown(doc) == "line one  \nline two"
