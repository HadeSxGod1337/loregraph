import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.longstoryshort.connector import (
    LINK_KIND_LSS_CHARACTER,
    SHARE_URL_RE,
    LssConfig,
    LssConnector,
)
from loregraph.connectors.longstoryshort.parser import parse_character
from loregraph.exceptions import ExternalDataParseError
from loregraph.schemas.connection import ConnectionEntityLinkOut
from loregraph.schemas.entity import EntityOut, FieldType

CHAR_ID = "69209705346bb5b024d5c110"
SHARE_URL = f"https://longstoryshort.app/characters/digital/{CHAR_ID}/"

# Real export file produced by longstoryshort.app ("Экспорт" on a sheet) —
# the canonical native-format fixture.
NATIVE_EXPORT_PATH = (
    Path(__file__).parent.parent
    / "lss_format_json_example"
    / "Виктория Виндель — Long Story Short.json"
)

# Golden fixture: flat shape (also the documented manual-JSON-paste format).
FLAT_SHEET = {
    "name": "Талия Ветрокрылая",
    "class": "Ranger",
    "race": "Wood Elf",
    "level": 5,
    "hp": 38,
    "ac": 15,
    "stats": {"str": 10, "dex": 18, "con": 12, "int": 11, "wis": 16, "cha": 9},
    "notes": "Ищет пропавшего брата.",
}

# Golden fixture: nested shape some exports use.
NESTED_SHEET = {
    "character": {"name": "Borin", "class": "Cleric", "level": 3},
    "vitality": {"hp-current": {"value": 21}, "ac": {"value": 18}},
    "abilities": {"str": {"score": 14}, "wis": {"score": 17}},
}


def test_parse_flat_sheet() -> None:
    name, fields = parse_character(FLAT_SHEET, SHARE_URL)
    assert name == "Талия Ветрокрылая"
    by_key = {f.key: f for f in fields}
    assert by_key["class"].value == "Ranger"
    assert by_key["ancestry"].value == "Wood Elf"
    assert by_key["level"].value == 5
    assert by_key["dex"].value == 18
    assert by_key["notes"].field_type is FieldType.RICH_TEXT
    assert by_key["character_sheet_url"].value == SHARE_URL


def test_parse_nested_sheet() -> None:
    name, fields = parse_character(NESTED_SHEET, None)
    assert name == "Borin"
    by_key = {f.key: f for f in fields}
    assert by_key["level"].value == 3
    assert by_key["hp"].value == 21
    assert by_key["ac"].value == 18
    assert by_key["str"].value == 14
    assert "character_sheet_url" not in by_key


def test_parse_without_name_raises() -> None:
    with pytest.raises(ExternalDataParseError):
        parse_character({"level": 3}, None)


def _pm_node_types(node: Any) -> set[str]:
    types: set[str] = set()
    if isinstance(node, dict):
        node_type = node.get("type")
        if isinstance(node_type, str):
            types.add(node_type)
        for child in node.get("content", []):
            types |= _pm_node_types(child)
    return types


def test_parse_native_export_file() -> None:
    """The real 'Виктория Виндель — Long Story Short.json' export: wrapper
    with a JSON-string `data` payload, {value:…} facts, TipTap text blocks."""
    data = json.loads(NATIVE_EXPORT_PATH.read_text(encoding="utf-8"))
    name, fields = parse_character(data, SHARE_URL)
    assert name == "Виктория Виндель"
    by_key = {f.key: f for f in fields}

    assert by_key["class"].value == "Воин 6 / Плут 1 (Мастер боевых искусств)"
    assert by_key["ancestry"].value == "Человек"
    assert by_key["background"].value == "Благородный"
    assert by_key["alignment"].value == "Хаотично-добрый"
    assert by_key["level"].value == 7
    assert by_key["experience"].value == 16800
    assert by_key["proficiency"].value == 3
    assert by_key["hp"].value == 36
    assert by_key["max_hp"].value == 69
    assert by_key["ac"].value == 17
    assert by_key["speed"].value == 30
    assert by_key["str"].value == 14
    assert by_key["dex"].value == 18
    assert by_key["cha"].value == 13
    assert by_key["avatar_url"].value.startswith("https://hotbox.longstoryshort")
    assert by_key["character_sheet_url"].value == SHARE_URL

    # Narrative TipTap blocks land as RICH_TEXT…
    for key in ("backstory", "personality", "ideals", "bonds", "flaws", "allies"):
        assert by_key[key].field_type is FieldType.RICH_TEXT, key
    backstory_json = json.dumps(by_key["backstory"].value, ensure_ascii=False)
    assert "Виктория Виндель из семьи спартанцев" in backstory_json
    # …sanitized: LSS's custom "resource" nodes must never reach the editor.
    for key in ("backstory", "personality", "ideals", "bonds", "flaws", "allies"):
        assert "resource" not in _pm_node_types(by_key[key].value), key
    # Mechanical blocks come in too — the sheet is printable from Loregraph,
    # so attacks/equipment/features have to survive the import.
    for key in (
        "attacks",
        "equipment",
        "features",
        "extra_features",
        "other_proficiencies",
        "treasures",
    ):
        assert by_key[key].field_type is FieldType.RICH_TEXT, key
        assert "resource" not in _pm_node_types(by_key[key].value), key

    # Proficiency flags drive the template's computed skills/saves.
    assert by_key["prof_save_dex"].value is True
    assert by_key["prof_save_str"].value is False
    assert by_key["prof_stealth"].value is True  # expertise (2) — still a flag
    assert by_key["prof_perception"].value is False
    assert by_key["prof_sleight_of_hand"].key == "prof_sleight_of_hand"  # not " "
    assert by_key["inspiration"].value is True

    assert by_key["age"].value == "21"
    assert by_key["eyes"].value == "серо-голубые"
    assert by_key["coins_gp"].value == 354
    assert by_key["temp_hp"].value == 0
    assert by_key["hit_die"].value == "d10"

    # The six notes-N boxes merge into one document, in order.
    notes_json = json.dumps(by_key["notes"].value, ensure_ascii=False)
    assert "Воинский адепт" in notes_json
    # Structured lists have no widget of their own — they arrive as text.
    weapons_json = json.dumps(by_key["weapons"].value, ensure_ascii=False)
    assert "Рапира" in weapons_json
    assert "Кости превосходства" in json.dumps(
        by_key["resources"].value, ensure_ascii=False
    )


def test_import_native_export_through_api(client: TestClient, project_id: str) -> None:
    connection_id = _make_connection(client, project_id)
    raw = NATIVE_EXPORT_PATH.read_text(encoding="utf-8")
    result = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {"raw_json": raw, "share_url": SHARE_URL}},
    ).json()
    assert result["created"] == 1, result

    entities = client.get(f"/api/projects/{project_id}/entities").json()
    victoria = next(e for e in entities if e["title"] == "Виктория Виндель")
    assert victoria["type"] == "party_member"
    by_key = {f["key"]: f for f in victoria["fields"]}
    assert by_key["level"]["value"] == 7
    assert by_key["backstory"]["field_type"] == "rich_text"

    # Binding the character to a sheet template must survive a refresh —
    # an update replaces the whole row, so the connector has to carry it.
    client.put(
        f"/api/projects/{project_id}/entities/{victoria['id']}",
        json={
            "type": victoria["type"],
            "title": victoria["title"],
            "fields": victoria["fields"],
            "template_id": "builtin_character",
        },
    )

    # Re-import of the same file refreshes in place (provenance by char id).
    again = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {"raw_json": raw, "share_url": SHARE_URL}},
    ).json()
    assert again["updated"] == 1 and again["created"] == 0

    refreshed = client.get(
        f"/api/projects/{project_id}/entities/{victoria['id']}"
    ).json()
    assert refreshed["template_id"] == "builtin_character"


def test_parse_spellcaster_export() -> None:
    """A caster's export: the spell list lives in `text.spells-level-N`
    blocks (not in `spells`, which only counts slots) — the shape the
    non-caster fixture above cannot exercise."""
    export = json.loads(
        (NATIVE_EXPORT_PATH.parent / "ВиВальди — Long Story Short.json").read_text(
            encoding="utf-8"
        )
    )
    _, fields = parse_character(export, None)
    by_key = {f.key: f for f in fields}

    spells = json.dumps(by_key["spells"].value, ensure_ascii=False)
    assert "Заговоры" in spells and "1 круг" in spells
    assert "Мистический снаряд" in spells
    # Empty levels contribute no heading of their own.
    assert "5 круг" not in spells

    # Slots are a separate field, and empty rows of them are not information.
    slots = json.dumps(by_key["spell_slots"].value, ensure_ascii=False)
    assert "Ячейки договора 2 круга — 2/2" in slots
    assert "0/0" not in slots

    assert by_key["caster_class"].value == "Колдун"
    # LSS computes these itself and leaves `value` empty — the number is in
    # customModifier, and the ability arrives as a code, not a name.
    assert by_key["spell_ability"].value == "Харизма"
    assert by_key["spell_save_dc"].value == "14"
    assert by_key["spell_attack"].value == "6"


def test_share_url_regex_extracts_24_hex_id() -> None:
    match = SHARE_URL_RE.search(SHARE_URL)
    assert match is not None and match.group("char_id") == CHAR_ID
    assert SHARE_URL_RE.search("https://longstoryshort.app/characters/list/") is None


def _make_connection(client: TestClient, project_id: str) -> str:
    resp = client.post(
        f"/api/projects/{project_id}/connections",
        json={"connector_type": "longstoryshort", "name": "LSS", "config": {}},
    )
    connection_id = resp.json()["id"]
    assert isinstance(connection_id, str)
    return connection_id


def test_import_from_raw_json_creates_party_member(
    client: TestClient, project_id: str
) -> None:
    connection_id = _make_connection(client, project_id)
    url = f"/api/projects/{project_id}/connections/{connection_id}/import"
    result = client.post(
        url,
        json={
            "payload": {
                "raw_json": json.dumps(FLAT_SHEET),
                "share_url": SHARE_URL,
            }
        },
    ).json()
    assert result["created"] == 1

    entities = client.get(f"/api/projects/{project_id}/entities").json()
    member = next(e for e in entities if e["type"] == "party_member")
    assert member["title"] == "Талия Ветрокрылая"
    sheet_url = next(f for f in member["fields"] if f["key"] == "character_sheet_url")
    assert sheet_url["value"] == SHARE_URL

    # Re-import (refresh): updates the same entity via provenance, and DM's
    # extra fields survive while sheet facts are overwritten (LWW per key).
    client.put(
        f"/api/projects/{project_id}/entities/{member['id']}",
        json={
            "type": "party_member",
            "title": member["title"],
            "fields": [
                {"key": "dm_secret", "field_type": "text", "value": "cursed"},
            ],
        },
    )
    refreshed_sheet = dict(FLAT_SHEET, level=6)
    again = client.post(
        url,
        json={
            "payload": {
                "raw_json": json.dumps(refreshed_sheet),
                "share_url": SHARE_URL,
            }
        },
    ).json()
    assert again["updated"] == 1 and again["created"] == 0

    updated = client.get(f"/api/projects/{project_id}/entities/{member['id']}").json()
    by_key = {f["key"]: f for f in updated["fields"]}
    assert by_key["level"]["value"] == 6
    assert by_key["dm_secret"]["value"] == "cursed"


def test_import_with_invalid_payload_is_422(
    client: TestClient, project_id: str
) -> None:
    connection_id = _make_connection(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {}},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "external_data_parse"


def test_import_with_bad_share_url_is_422(client: TestClient, project_id: str) -> None:
    connection_id = _make_connection(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {"share_url": "https://example.com/nope"}},
    )
    assert resp.status_code == 422


def test_import_array_wrapped_json(client: TestClient, project_id: str) -> None:
    """Batch export where the top level is an array of character objects."""
    connection_id = _make_connection(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={
            "payload": {
                "raw_json": json.dumps([FLAT_SHEET]),
            }
        },
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == 1


def test_import_nested_wrapper_json(client: TestClient, project_id: str) -> None:
    """LSS export wrapped in a metadata envelope: {\"characters\": [...]}."""
    connection_id = _make_connection(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={
            "payload": {
                "raw_json": json.dumps({"characters": [FLAT_SHEET], "version": 2}),
            }
        },
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == 1


def test_import_binds_the_character_template(
    client: TestClient, project_id: str
) -> None:
    """An imported sheet is a character sheet — it must arrive already bound
    to the party-member template, not as a field list the DM binds by hand."""
    connection_id = _make_connection(client, project_id)
    client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {"raw_json": json.dumps(FLAT_SHEET)}},
    )
    entities = client.get(f"/api/projects/{project_id}/entities").json()
    member = next(e for e in entities if e["type"] == "party_member")
    assert member["template_id"] == "builtin_character"


def test_import_prefers_the_projects_own_party_member_template(
    client: TestClient, project_id: str
) -> None:
    own = client.post(
        f"/api/projects/{project_id}/templates",
        json={
            "name": "Наш лист",
            "entity_type": "party_member",
            "field_defs": [
                {"key": "class", "field_type": "text", "label": "Класс"},
            ],
            "layout": {"sections": []},
        },
    )
    assert own.status_code == 201, own.text
    connection_id = _make_connection(client, project_id)
    client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {"raw_json": json.dumps(FLAT_SHEET)}},
    )
    entities = client.get(f"/api/projects/{project_id}/entities").json()
    member = next(e for e in entities if e["type"] == "party_member")
    assert member["template_id"] == own.json()["id"]


def test_import_of_several_documents_reports_each_by_name(
    client: TestClient, project_id: str
) -> None:
    """A party arrives as one file per character. One broken file must cost
    exactly that character, not the whole party."""
    connection_id = _make_connection(client, project_id)
    result = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={
            "payload": {
                "documents": [
                    {"name": "Талия.json", "content": json.dumps(FLAT_SHEET)},
                    {"name": "Борин.json", "content": json.dumps(NESTED_SHEET)},
                    {"name": "битый.json", "content": "{not json"},
                ]
            }
        },
    ).json()

    assert result["created"] == 2
    assert [item["title"] for item in result["items"]] == [
        "Талия Ветрокрылая",
        "Borin",
    ]
    assert all(item["action"] == "created" for item in result["items"])
    assert [error["ref"] for error in result["errors"]] == ["битый.json"]
    assert result["skipped"] == 1


def test_import_of_every_real_export_at_once(
    client: TestClient, project_id: str
) -> None:
    """The whole lss_format_json_example/ folder in one run — the shape a DM
    actually produces: one native export file per player."""
    exports = sorted(NATIVE_EXPORT_PATH.parent.glob("*.json"))
    connection_id = _make_connection(client, project_id)
    result = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={
            "payload": {
                "documents": [
                    {"name": path.name, "content": path.read_text(encoding="utf-8")}
                    for path in exports
                ]
            }
        },
    ).json()

    assert result["created"] == len(exports), result
    assert result["errors"] == []
    entities = client.get(f"/api/projects/{project_id}/entities").json()
    assert all(e["template_id"] == "builtin_character" for e in entities)


def test_import_array_document_takes_every_character(
    client: TestClient, project_id: str
) -> None:
    connection_id = _make_connection(client, project_id)
    result = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {"raw_json": json.dumps([FLAT_SHEET, NESTED_SHEET])}},
    ).json()
    assert result["created"] == 2
    # A share URL identifies one sheet, so a batch gets none stamped on it.
    entities = client.get(f"/api/projects/{project_id}/entities").json()
    assert all(
        "character_sheet_url" not in {f["key"] for f in e["fields"]} for e in entities
    )


class _OneLinkStore:
    """Just enough ConnectionEntityLinkStore for the live-source path."""

    def __init__(self, entity_id: str) -> None:
        self._entity_id = entity_id

    async def list_for_connection(
        self, connection_id: str
    ) -> list[ConnectionEntityLinkOut]:
        return [
            ConnectionEntityLinkOut(
                id="link1",
                connection_id=connection_id,
                entity_id=self._entity_id,
                external_id=CHAR_ID,
                external_kind=LINK_KIND_LSS_CHARACTER,
                last_synced_at=datetime.now(UTC),
            )
        ]


class _OneEntityStore:
    def __init__(self, entity: EntityOut) -> None:
        self._entity = entity

    async def get(self, entity_id: str) -> EntityOut:
        assert entity_id == self._entity.id
        return self._entity


@pytest.mark.asyncio
async def test_grounding_falls_back_to_the_last_imported_sheet(
    client: TestClient, project_id: str
) -> None:
    """LSS publishes no JSON endpoint we may call, so the live fetch fails
    for everyone. Grounding must still answer with the imported state
    instead of silently contributing nothing at all."""
    connection_id = _make_connection(client, project_id)
    client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {"raw_json": json.dumps(FLAT_SHEET), "share_url": SHARE_URL}},
    )
    entities = client.get(f"/api/projects/{project_id}/entities").json()
    member = EntityOut.model_validate(
        next(e for e in entities if e["type"] == "party_member")
    )

    context = ConnectorContext(
        project_id=project_id,
        connection_id=connection_id,
        connection_name="LSS",
        entity_service=cast(Any, None),
        edge_service=cast(Any, None),
        entity_store=cast(Any, _OneEntityStore(member)),
        edge_store=cast(Any, None),
        attachment_store=cast(Any, None),
        attachments_dir=cast(Any, None),
        link_store=cast(Any, _OneLinkStore(member.id)),
    )
    chunks = await LssConnector(LssConfig(), context).query("")

    assert len(chunks) == 1
    assert chunks[0].title == "Талия Ветрокрылая"
    assert "level: 5" in chunks[0].text
    # Labelled, so neither the DM nor the model reads stale HP as current.
    assert chunks[0].kind == "character (as last imported)"


def test_parse_character_error_includes_top_level_keys() -> None:
    """When name is not found, the error lists the top-level keys for debugging."""
    with pytest.raises(ExternalDataParseError, match="top-level keys"):
        parse_character({"foo": 1, "bar": 2}, None)
