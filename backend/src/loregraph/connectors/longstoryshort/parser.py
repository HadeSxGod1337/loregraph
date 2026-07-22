"""LongStoryShort character JSON -> Loregraph entity fields.

Two shapes are understood:

1. **Native LSS export** (the file "… — Long Story Short.json" the site
   produces; see backend/lss_format_json_example/): a wrapper
   ``{"jsonType": "character", "version": "2", "data": "<JSON string>"}``
   whose inner document keeps facts as ``{"value": …}`` objects
   (``name.value``, ``info.charClass.value``, ``vitality.hp-current.value``,
   ``stats.str.score``) and narrative blocks as TipTap/ProseMirror docs under
   ``text.*.value.data``. Those docs are imported as RICH_TEXT after
   sanitization (LSS uses custom nodes like ``resource`` that our editor
   doesn't know).

2. **Anything else** — a tolerant fallback that looks for a character's
   facts under several plausible key paths and skips what it can't find.

The only hard requirement is a character name. Field keys are stable
Loregraph conventions (``class``, ``level``, ``character_sheet_url``…) —
the frontend keys the iframe embed off ``character_sheet_url``.
"""

import json
from typing import Any

from loregraph.connectors.markdown_codec import markdown_to_prosemirror
from loregraph.exceptions import ExternalDataParseError
from loregraph.schemas.entity import EntityFieldIn, FieldType

PARTY_MEMBER_TYPE = "party_member"
CHARACTER_SHEET_URL_KEY = "character_sheet_url"

_NAME_PATHS: list[tuple[str, ...]] = [
    ("name",),
    ("name", "value"),
    ("characterName",),
    ("charName",),
    ("character", "name"),
    ("info", "name"),
    ("data", "name"),
]
_TEXT_FIELDS: dict[str, list[tuple[str, ...]]] = {
    "class": [
        ("class",),
        ("className",),
        ("character", "class"),
        ("info", "class"),
        ("info", "charClass", "value"),
    ],
    "subclass": [
        ("subclass",),
        ("subclassName",),
        ("info", "charSubclass", "value"),
    ],
    "ancestry": [
        ("race",),
        ("ancestry",),
        ("character", "race"),
        ("info", "race"),
        ("info", "race", "value"),
    ],
    "background": [
        ("background",),
        ("info", "background"),
        ("info", "background", "value"),
    ],
    "alignment": [
        ("alignment",),
        ("info", "alignment"),
        ("info", "alignment", "value"),
    ],
}
_NUMBER_FIELDS: dict[str, list[tuple[str, ...]]] = {
    "level": [
        ("level",),
        ("info", "level"),
        ("character", "level"),
        ("info", "level", "value"),
    ],
    "experience": [("experience",), ("info", "experience", "value")],
    "proficiency": [("proficiency",)],
    "hp": [("hp",), ("hitPoints",), ("vitality", "hp-current", "value")],
    "max_hp": [("maxHp",), ("hpMax",), ("vitality", "hp-max", "value")],
    "ac": [("ac",), ("armorClass",), ("vitality", "ac", "value")],
    "speed": [("speed",), ("vitality", "speed", "value")],
}
_ABILITY_CONTAINERS: list[tuple[str, ...]] = [("stats",), ("abilities",), ("scores",)]
_ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")
_NOTES_PATHS: list[tuple[str, ...]] = [("notes",), ("bio",), ("biography",)]
_AVATAR_PATHS: list[tuple[str, ...]] = [("avatar", "jpeg"), ("avatar", "webp")]

# Narrative TipTap blocks of the native export worth having in a lore tool,
# as our field key -> LSS block name. Mechanical blocks (attacks, traits,
# prof, notes-N…) are deliberately skipped: the sheet stays the source of
# truth for mechanics, the iframe embed shows them live.
_NATIVE_TEXT_BLOCKS: dict[str, str] = {
    "backstory": "background",
    "personality": "personality",
    "ideals": "ideals",
    "bonds": "bonds",
    "flaws": "flaws",
    "allies": "allies",
    "quests": "quests",
}

# ProseMirror node/mark types our editor renders (StarterKit v3 + Image +
# Underline + entityLink). Anything else in an LSS doc (e.g. their custom
# "resource" node) is stripped so a stored doc can never break the editor.
_ALLOWED_PM_NODES = frozenset(
    {
        "doc",
        "paragraph",
        "text",
        "heading",
        "bulletList",
        "orderedList",
        "listItem",
        "blockquote",
        "codeBlock",
        "horizontalRule",
        "hardBreak",
        "image",
    }
)
_ALLOWED_PM_MARKS = frozenset({"bold", "italic", "strike", "underline", "code", "link"})


def parse_character(
    data: dict[str, Any], share_url: str | None
) -> tuple[str, list[EntityFieldIn]]:
    """Returns (character name, entity fields). Raises ExternalDataParseError
    when no name can be located anywhere in the document."""
    data = _unwrap_native_export(data)
    name = _first_string(data, _NAME_PATHS)
    if name is None:
        keys = ", ".join(sorted(data.keys())) if data else "(empty dict)"
        raise ExternalDataParseError(
            "longstoryshort",
            f"character name not found (looked under: name.value, name, "
            f"characterName, character.name, info.name, data.name; "
            f"top-level keys: {keys})",
        )

    fields: list[EntityFieldIn] = []
    for key, paths in _TEXT_FIELDS.items():
        value = _first_string(data, paths)
        if value:
            fields.append(
                EntityFieldIn(
                    key=key,
                    field_type=FieldType.TEXT,
                    value=value,
                    show_on_card=key in ("class", "ancestry"),
                )
            )
    for key, paths in _NUMBER_FIELDS.items():
        number = _first_number(data, paths)
        if number is not None:
            fields.append(
                EntityFieldIn(
                    key=key,
                    field_type=FieldType.NUMBER,
                    value=number,
                    show_on_card=key == "level",
                )
            )
    for container_path in _ABILITY_CONTAINERS:
        container = _dig(data, container_path)
        if isinstance(container, dict):
            for ability in _ABILITY_KEYS:
                raw = container.get(ability)
                if isinstance(raw, dict):
                    raw = None  # dict means nested — try sub-paths below
                score = _coerce_number(
                    raw
                    or _dig(container, (ability, "score"))
                    or _dig(container, (ability, "value"))
                )
                if score is not None:
                    fields.append(
                        EntityFieldIn(
                            key=ability, field_type=FieldType.NUMBER, value=score
                        )
                    )
            break

    fields.extend(_native_text_fields(data))

    notes = _first_string(data, _NOTES_PATHS)
    if notes:
        fields.append(
            EntityFieldIn(
                key="notes",
                field_type=FieldType.RICH_TEXT,
                value=markdown_to_prosemirror(notes),
            )
        )
    avatar_url = _first_string(data, _AVATAR_PATHS)
    if avatar_url:
        fields.append(
            EntityFieldIn(key="avatar_url", field_type=FieldType.TEXT, value=avatar_url)
        )
    if share_url:
        fields.append(
            EntityFieldIn(
                key=CHARACTER_SHEET_URL_KEY,
                field_type=FieldType.TEXT,
                value=share_url,
            )
        )
    return name, fields


def _unwrap_native_export(data: dict[str, Any]) -> dict[str, Any]:
    """The site's export file wraps the sheet as
    ``{"jsonType": "character", "data": "<JSON string>"}`` — unwrap it.
    A dict ``data`` payload (future format change?) unwraps too."""
    inner = data.get("data")
    if isinstance(inner, str) and data.get("jsonType") == "character":
        try:
            parsed = json.loads(inner)
        except json.JSONDecodeError as e:
            raise ExternalDataParseError(
                "longstoryshort", f"export 'data' field is not valid JSON: {e}"
            ) from e
        if isinstance(parsed, dict):
            return parsed
    if isinstance(inner, dict) and (
        "name" in inner or inner.get("jsonType") == "character"
    ):
        return inner
    return data


def _native_text_fields(data: dict[str, Any]) -> list[EntityFieldIn]:
    fields: list[EntityFieldIn] = []
    text_blocks = data.get("text")
    if not isinstance(text_blocks, dict):
        return fields
    for field_key, block_name in _NATIVE_TEXT_BLOCKS.items():
        doc = _dig(text_blocks, (block_name, "value", "data"))
        if not isinstance(doc, dict) or doc.get("type") != "doc":
            continue
        sanitized = _sanitize_prosemirror(doc)
        if sanitized is not None:
            fields.append(
                EntityFieldIn(
                    key=field_key,
                    field_type=FieldType.RICH_TEXT,
                    value=sanitized,
                )
            )
    return fields


def _sanitize_prosemirror(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only node/mark types our editor knows; drop the rest (LSS's
    ``resource`` nodes etc.). Returns None when nothing textual survives."""
    sanitized = _sanitize_pm_node(doc)
    if sanitized is None:
        return None
    if not _pm_has_text(sanitized):
        return None
    return sanitized


def _sanitize_pm_node(node: dict[str, Any]) -> dict[str, Any] | None:
    node_type = node.get("type")
    if node_type not in _ALLOWED_PM_NODES:
        return None
    clean: dict[str, Any] = {"type": node_type}
    if isinstance(node.get("attrs"), dict):
        clean["attrs"] = node["attrs"]
    if node_type == "text":
        text = node.get("text")
        if not isinstance(text, str) or not text:
            return None
        clean["text"] = text
        marks = [
            mark
            for mark in node.get("marks", [])
            if isinstance(mark, dict) and mark.get("type") in _ALLOWED_PM_MARKS
        ]
        if marks:
            clean["marks"] = marks
        return clean
    content = node.get("content")
    if isinstance(content, list):
        children = [
            child_clean
            for child in content
            if isinstance(child, dict)
            and (child_clean := _sanitize_pm_node(child)) is not None
        ]
        if children:
            clean["content"] = children
    # Containers that lost all their children carry no information.
    if node_type in ("bulletList", "orderedList", "listItem", "blockquote") and (
        not clean.get("content")
    ):
        return None
    return clean


def _pm_has_text(node: dict[str, Any]) -> bool:
    if node.get("type") == "text":
        text = node.get("text", "")
        return isinstance(text, str) and bool(text.strip())
    return any(
        _pm_has_text(child)
        for child in node.get("content", [])
        if isinstance(child, dict)
    )


def _dig(data: Any, path: tuple[str, ...]) -> Any:
    node = data
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _first_string(data: dict[str, Any], paths: list[tuple[str, ...]]) -> str | None:
    for path in paths:
        value = _dig(data, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _coerce_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None
    return None


def _first_number(
    data: dict[str, Any], paths: list[tuple[str, ...]]
) -> int | float | None:
    for path in paths:
        number = _coerce_number(_dig(data, path))
        if number is not None:
            return number
    return None
