"""Tests for [[label]] wikilink → ProseMirror conversion in commit.py."""


from loregraph.agent.nodes.commit import _wikilinks_to_prosemirror


class TestWikilinksToProseMirror:
    def test_plain_text_no_links(self) -> None:
        result = _wikilinks_to_prosemirror("Hello world", {})
        assert result == {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
        }

    def test_single_link(self) -> None:
        title_to_id = {"mira kuznetz": "abc123"}
        result = _wikilinks_to_prosemirror("Talk to [[Mira Kuznetz]].", title_to_id)
        assert result["type"] == "doc"
        para = result["content"][0]
        assert para["type"] == "paragraph"
        content = para["content"]
        assert len(content) == 3
        assert content[0] == {"type": "text", "text": "Talk to "}
        assert content[1] == {
            "type": "entityLink",
            "attrs": {"entityId": "abc123", "fieldKey": None, "label": "Mira Kuznetz"},
        }
        assert content[2] == {"type": "text", "text": "."}

    def test_multiple_links(self) -> None:
        title_to_id = {"mira kuznetz": "abc", "iron forge": "def"}
        result = _wikilinks_to_prosemirror(
            "[[Mira Kuznetz]] works at [[The Iron Forge]].", title_to_id
        )
        content = result["content"][0]["content"]
        # [[Mira Kuznetz]] -> resolved,
        # [[The Iron Forge]] -> unresolved (title mismatch)
        assert content[0]["type"] == "entityLink"
        assert content[0]["attrs"]["entityId"] == "abc"
        # "The Iron Forge" not in map (lowercase "the iron forge" not in map)
        assert content[2]["type"] == "entityLink"
        assert content[2]["attrs"]["entityId"] == ""

    def test_case_insensitive_lookup(self) -> None:
        title_to_id = {"mira kuznetz": "abc123"}
        result = _wikilinks_to_prosemirror("[[mira kuznetz]]", title_to_id)
        link = result["content"][0]["content"][0]
        assert link["attrs"]["entityId"] == "abc123"

    def test_paragraphs_separated_by_double_newline(self) -> None:
        title_to_id = {"loc": "id1"}
        result = _wikilinks_to_prosemirror("First [[Loc]].\n\nSecond.", title_to_id)
        assert len(result["content"]) == 2
        assert result["content"][0]["content"][1]["attrs"]["label"] == "Loc"
        assert result["content"][1]["content"][0]["text"] == "Second."

    def test_hard_break_for_single_newline(self) -> None:
        result = _wikilinks_to_prosemirror("Line one\nLine two", {})
        content = result["content"][0]["content"]
        assert len(content) == 3
        assert content[1] == {"type": "hardBreak"}

    def test_empty_text(self) -> None:
        result = _wikilinks_to_prosemirror("", {})
        assert result["type"] == "doc"
        assert len(result["content"]) == 1  # single empty paragraph

    def test_only_wikilinks(self) -> None:
        title_to_id = {"a": "id_a", "b": "id_b"}
        result = _wikilinks_to_prosemirror("[[A]] and [[B]]", title_to_id)
        content = result["content"][0]["content"]
        assert content[0]["attrs"]["entityId"] == "id_a"
        assert content[1] == {"type": "text", "text": " and "}
        assert content[2]["attrs"]["entityId"] == "id_b"
