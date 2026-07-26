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
    "player_name": [("playerName",), ("info", "playerName", "value")],
    "hit_die": [("hitDie",), ("vitality", "hit-die", "value")],
    "caster_class": [("casterClass", "value")],
    # LSS leaves `value` empty when the number is computed on their sheet and
    # keeps the DM's override in `customModifier` — read both.
    "spell_save_dc": [
        ("spellsInfo", "save", "value"),
        ("spellsInfo", "save", "customModifier"),
    ],
    "spell_attack": [
        ("spellsInfo", "mod", "value"),
        ("spellsInfo", "mod", "customModifier"),
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
    "temp_hp": [("tempHp",), ("vitality", "hp-temp", "value")],
    "hit_dice_current": [("vitality", "hp-dice-current", "value")],
    "exhaustion": [("exhaustion",)],
}
# subInfo values are free text on the LSS sheet ("178", "178 см") — imported
# as text so nothing is lost to a failed int() parse.
_SUB_INFO_KEYS = ("age", "height", "weight", "eyes", "skin", "hair")
_COIN_KEYS = ("pp", "gp", "ep", "sp", "cp")
_ABILITY_CONTAINERS: list[tuple[str, ...]] = [("stats",), ("abilities",), ("scores",)]
_ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")
# The spellcasting ability arrives as a code (`spellsInfo.base.code`), not a
# name, whenever LSS computes the number itself.
_ABILITY_LABELS: dict[str, str] = {
    "str": "Сила",
    "dex": "Ловкость",
    "con": "Телосложение",
    "int": "Интеллект",
    "wis": "Мудрость",
    "cha": "Харизма",
}
_NOTES_PATHS: list[tuple[str, ...]] = [("notes",), ("bio",), ("biography",)]
_AVATAR_PATHS: list[tuple[str, ...]] = [("avatar", "jpeg"), ("avatar", "webp")]

# Every TipTap block of the native export, as our field key -> LSS block name.
# The mechanical ones (attacks, equipment, features, traits, prof, items) used
# to be skipped on the grounds that the live embed shows them — but the sheet
# is printable from Loregraph now, and a printed sheet without attacks or
# equipment is not a character sheet.
_NATIVE_TEXT_BLOCKS: dict[str, str] = {
    "backstory": "background",
    "personality": "personality",
    "ideals": "ideals",
    "bonds": "bonds",
    "flaws": "flaws",
    "allies": "allies",
    "quests": "quests",
    "attacks": "attacks",
    "equipment": "equipment",
    "features": "features",
    "extra_features": "traits",
    "other_proficiencies": "prof",
    "treasures": "items",
}
# LSS splits free notes across six fixed boxes; they carry no headings of
# their own, so they are concatenated into one `notes` document in order.
_NATIVE_NOTE_BLOCKS = tuple(f"notes-{index}" for index in range(1, 7))

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

    fields.extend(_sub_info_fields(data))
    fields.extend(_coin_fields(data))
    fields.extend(_proficiency_flag_fields(data))
    fields.extend(_native_text_fields(data))
    fields.extend(_table_fields(data))

    spell_ability = _first_string(
        data, [("spellsInfo", "base", "value")]
    ) or _ABILITY_LABELS.get(
        _first_string(data, [("spellsInfo", "base", "code")]) or ""
    )
    if spell_ability:
        fields.append(
            EntityFieldIn(
                key="spell_ability", field_type=FieldType.TEXT, value=spell_ability
            )
        )

    inspiration = data.get("inspiration")
    if isinstance(inspiration, bool):
        fields.append(
            EntityFieldIn(
                key="inspiration", field_type=FieldType.BOOLEAN, value=inspiration
            )
        )

    notes = _first_string(data, _NOTES_PATHS)
    if notes:
        fields.append(
            EntityFieldIn(
                key="notes",
                field_type=FieldType.RICH_TEXT,
                value=markdown_to_prosemirror(notes),
            )
        )
    else:
        native_notes = _native_notes(data)
        if native_notes is not None:
            fields.append(
                EntityFieldIn(
                    key="notes", field_type=FieldType.RICH_TEXT, value=native_notes
                )
            )
    spell_list = _spell_list(data)
    if spell_list is not None:
        fields.append(
            EntityFieldIn(
                key="spells", field_type=FieldType.RICH_TEXT, value=spell_list
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


def _sub_info_fields(data: dict[str, Any]) -> list[EntityFieldIn]:
    sub_info = data.get("subInfo")
    if not isinstance(sub_info, dict):
        return []
    fields: list[EntityFieldIn] = []
    for key in _SUB_INFO_KEYS:
        value = _first_string(sub_info, [(key, "value"), (key,)])
        if value:
            fields.append(
                EntityFieldIn(key=key, field_type=FieldType.TEXT, value=value)
            )
    return fields


def _coin_fields(data: dict[str, Any]) -> list[EntityFieldIn]:
    coins = data.get("coins")
    if not isinstance(coins, dict):
        return []
    fields: list[EntityFieldIn] = []
    for key in _COIN_KEYS:
        amount = _first_number(coins, [(key, "value"), (key,)])
        if amount is not None:
            fields.append(
                EntityFieldIn(
                    key=f"coins_{key}", field_type=FieldType.NUMBER, value=amount
                )
            )
    return fields


def _proficiency_flag_fields(data: dict[str, Any]) -> list[EntityFieldIn]:
    """LSS's save/skill proficiency flags -> the booleans the built-in
    Character template's formulas read. Without them an imported character
    shows every skill at its bare ability modifier.

    LSS grades skills 0/1/2 (none/proficient/expertise) and our sheet has one
    checkbox, so expertise imports as plain proficiency — the doubled bonus is
    the one thing that needs re-adding by hand.
    """
    fields: list[EntityFieldIn] = []
    saves = data.get("saves")
    if isinstance(saves, dict):
        for ability in _ABILITY_KEYS:
            entry = saves.get(ability)
            if isinstance(entry, dict):
                fields.append(
                    EntityFieldIn(
                        key=f"prof_save_{ability}",
                        field_type=FieldType.BOOLEAN,
                        value=_is_proficient(entry.get("isProf")),
                    )
                )
    skills = data.get("skills")
    if isinstance(skills, dict):
        for name, entry in skills.items():
            if not isinstance(entry, dict):
                continue
            fields.append(
                EntityFieldIn(
                    # "sleight of hand" -> "sleight_of_hand"
                    key=f"prof_{name.replace(' ', '_')}",
                    field_type=FieldType.BOOLEAN,
                    value=_is_proficient(entry.get("isProf")),
                )
            )
    return fields


def _is_proficient(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return isinstance(raw, int | float) and raw >= 1


def _table_fields(data: dict[str, Any]) -> list[EntityFieldIn]:
    """The export's structured lists (weapons, resources, spell slots) have no
    matching widget on a Loregraph sheet, so each becomes a plain rich-text
    block — readable and printable, which is what they are needed for."""
    fields: list[EntityFieldIn] = []
    weapons = [
        line
        for entry in data.get("weaponsList") or []
        if isinstance(entry, dict) and (line := _weapon_line(entry))
    ]
    if weapons:
        fields.append(
            EntityFieldIn(
                key="weapons",
                field_type=FieldType.RICH_TEXT,
                value=_paragraphs(weapons),
            )
        )

    resources = data.get("resources")
    if isinstance(resources, dict):
        lines = [
            line
            for entry in resources.values()
            if isinstance(entry, dict) and (line := _resource_line(entry))
        ]
        if lines:
            fields.append(
                EntityFieldIn(
                    key="resources",
                    field_type=FieldType.RICH_TEXT,
                    value=_paragraphs(lines),
                )
            )

    slot_lines = _spell_slot_lines(data)
    if slot_lines:
        fields.append(
            EntityFieldIn(
                key="spell_slots",
                field_type=FieldType.RICH_TEXT,
                value=_paragraphs(slot_lines),
            )
        )

    attunements = [
        line
        for entry in data.get("attunementsList") or []
        if isinstance(entry, dict)
        and (line := _first_string(entry, [("value",), ("name", "value"), ("name",)]))
    ]
    if attunements:
        fields.append(
            EntityFieldIn(
                key="attunements",
                field_type=FieldType.RICH_TEXT,
                value=_paragraphs(attunements),
            )
        )
    return fields


def _weapon_line(entry: dict[str, Any]) -> str | None:
    name = _first_string(entry, [("name", "value"), ("name",)])
    if not name:
        return None
    parts = [name]
    modifier = _first_string(entry, [("mod", "value"), ("mod",)])
    damage = _first_string(entry, [("dmg", "value"), ("dmg",)])
    if modifier:
        parts.append(f"атака {modifier}")
    if damage:
        parts.append(damage)
    return " — ".join([parts[0], ", ".join(parts[1:])]) if len(parts) > 1 else parts[0]


def _resource_line(entry: dict[str, Any]) -> str | None:
    name = _first_string(entry, [("name",)])
    if not name:
        return None
    current = _coerce_number(entry.get("current"))
    maximum = _coerce_number(entry.get("max"))
    if current is None and maximum is None:
        return name
    shown_current = "?" if current is None else current
    shown_maximum = "?" if maximum is None else maximum
    return f"{name} — {shown_current}/{shown_maximum}"


def _spell_slot_lines(data: dict[str, Any]) -> list[str]:
    """Spell and pact-magic slot counters. The spells themselves are *not*
    here — LSS keeps the list in the `text` blocks (see _spell_list)."""
    lines: list[str] = []
    for container_key, label in (("spells", ""), ("spellsPact", " договора")):
        container = data.get(container_key)
        if not isinstance(container, dict):
            continue
        for key, entry in sorted(container.items()):
            if not key.startswith("slots-"):
                continue
            total = (
                _coerce_number(entry.get("value")) if isinstance(entry, dict) else None
            )
            # An empty row of slots is sheet scaffolding, not information.
            if not total:
                continue
            used = _coerce_number(entry.get("filled")) or 0
            level = key.removeprefix("slots-")
            lines.append(f"Ячейки{label} {level} круга — {used}/{total}")
    return lines


def _paragraphs(lines: list[str]) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            for line in lines
        ],
    }


def _spell_list(data: dict[str, Any]) -> dict[str, Any] | None:
    """The spell list — one `text` block per spell level (`spells-level-0` …
    `spells-level-9`), same TipTap shape as the narrative blocks.

    They are merged into a single document with a heading per level, because
    a sheet field holds one document and nine near-empty fields would be worse
    than one list. Empty levels are dropped.
    """
    text_blocks = data.get("text")
    if not isinstance(text_blocks, dict):
        return None
    content: list[dict[str, Any]] = []
    for level in range(10):
        doc = _dig(text_blocks, (f"spells-level-{level}", "value", "data"))
        if not isinstance(doc, dict) or doc.get("type") != "doc":
            continue
        sanitized = _sanitize_prosemirror(doc)
        if sanitized is None:
            continue
        content.append(
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [
                    {
                        "type": "text",
                        "text": "Заговоры" if level == 0 else f"{level} круг",
                    }
                ],
            }
        )
        content.extend(sanitized.get("content", []))
    return {"type": "doc", "content": content} if content else None


def _native_notes(data: dict[str, Any]) -> dict[str, Any] | None:
    text_blocks = data.get("text")
    if not isinstance(text_blocks, dict):
        return None
    content: list[dict[str, Any]] = []
    for block_name in _NATIVE_NOTE_BLOCKS:
        doc = _dig(text_blocks, (block_name, "value", "data"))
        if not isinstance(doc, dict) or doc.get("type") != "doc":
            continue
        sanitized = _sanitize_prosemirror(doc)
        if sanitized is not None:
            content.extend(sanitized.get("content", []))
    return {"type": "doc", "content": content} if content else None


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
