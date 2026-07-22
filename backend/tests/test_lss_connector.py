import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loregraph.connectors.longstoryshort.connector import SHARE_URL_RE
from loregraph.connectors.longstoryshort.parser import parse_character
from loregraph.exceptions import ExternalDataParseError
from loregraph.schemas.entity import FieldType

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
    # Mechanical blocks stay out on purpose (sheet is the source of truth).
    assert "attacks" not in by_key
    assert "traits" not in by_key


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

    # Re-import of the same file refreshes in place (provenance by char id).
    again = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {"raw_json": raw, "share_url": SHARE_URL}},
    ).json()
    assert again["updated"] == 1 and again["created"] == 0


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


def test_parse_character_error_includes_top_level_keys() -> None:
    """When name is not found, the error lists the top-level keys for debugging."""
    with pytest.raises(ExternalDataParseError, match="top-level keys"):
        parse_character({"foo": 1, "bar": 2}, None)
