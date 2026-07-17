"""LongStoryShort character JSON -> Loregraph entity fields.

LSS has no public API and no documented schema, so this parser is
deliberately tolerant: it looks for a character's facts under several
plausible key paths and simply skips whatever it can't find. The only hard
requirement is a character name — without one there is nothing to import.

Field keys are stable Loregraph conventions (``class``, ``level``,
``character_sheet_url``…) — the frontend keys the iframe embed off
``character_sheet_url``.
"""

from typing import Any

from loregraph.connectors.markdown_codec import markdown_to_prosemirror
from loregraph.exceptions import ExternalDataParseError
from loregraph.schemas.entity import EntityFieldIn, FieldType

PARTY_MEMBER_TYPE = "party_member"
CHARACTER_SHEET_URL_KEY = "character_sheet_url"

_NAME_PATHS: list[tuple[str, ...]] = [
    ("name",),
    ("characterName",),
    ("charName",),
    ("character", "name"),
    ("info", "name"),
    ("data", "name"),
]
_TEXT_FIELDS: dict[str, list[tuple[str, ...]]] = {
    "class": [("class",), ("className",), ("character", "class"), ("info", "class")],
    "subclass": [("subclass",), ("subclassName",)],
    "ancestry": [("race",), ("ancestry",), ("character", "race"), ("info", "race")],
    "background": [("background",), ("info", "background")],
    "alignment": [("alignment",), ("info", "alignment")],
}
_NUMBER_FIELDS: dict[str, list[tuple[str, ...]]] = {
    "level": [("level",), ("info", "level"), ("character", "level")],
    "hp": [("hp",), ("hitPoints",), ("vitality", "hp-current", "value")],
    "max_hp": [("maxHp",), ("hpMax",), ("vitality", "hp-max", "value")],
    "ac": [("ac",), ("armorClass",), ("vitality", "ac", "value")],
    "speed": [("speed",), ("vitality", "speed", "value")],
}
_ABILITY_CONTAINERS: list[tuple[str, ...]] = [("stats",), ("abilities",), ("scores",)]
_ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")
_NOTES_PATHS: list[tuple[str, ...]] = [
    ("notes",),
    ("bio",),
    ("biography",),
    ("text", "background", "value", "data", "text"),
]


def parse_character(
    data: dict[str, Any], share_url: str | None
) -> tuple[str, list[EntityFieldIn]]:
    """Returns (character name, entity fields). Raises ExternalDataParseError
    when no name can be located anywhere in the document."""
    name = _first_string(data, _NAME_PATHS)
    if name is None:
        raise ExternalDataParseError(
            "longstoryshort",
            "character name not found (looked under: name, "
            "characterName, character.name, info.name, data.name)",
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

    notes = _first_string(data, _NOTES_PATHS)
    if notes:
        fields.append(
            EntityFieldIn(
                key="notes",
                field_type=FieldType.RICH_TEXT,
                value=markdown_to_prosemirror(notes),
            )
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
