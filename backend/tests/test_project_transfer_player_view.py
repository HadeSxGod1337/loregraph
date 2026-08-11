from fastapi.testclient import TestClient


def _doc(text: str) -> dict[str, object]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def test_player_view_survives_export_import(
    client: TestClient, project_id: str
) -> None:
    entity = client.post(
        f"/api/projects/{project_id}/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [
                {"key": "faction", "field_type": "text", "value": "Guild"},
                {"key": "secret", "field_type": "text", "value": "double agent"},
            ],
        },
    ).json()

    # Reveal, write player text, expose only the faction field.
    client.put(
        f"/api/projects/{project_id}/entities/{entity['id']}/player-view",
        json={
            "revealed_to_players": True,
            "player_text": _doc("A friendly smith."),
            "visible_field_keys": ["faction"],
        },
    )

    export = client.get(f"/api/projects/{project_id}/export").json()
    imported = client.post("/api/projects/import", json=export).json()

    entities = client.get(f"/api/projects/{imported['id']}/entities").json()
    mira = next(e for e in entities if e["title"] == "Mira")
    assert mira["revealed_to_players"] is True
    assert mira["player_text"]["content"][0]["content"][0]["text"] == (
        "A friendly smith."
    )
    by_key = {f["key"]: f for f in mira["fields"]}
    assert by_key["faction"]["visible_to_players"] is True
    assert by_key["secret"]["visible_to_players"] is False


def test_old_export_without_player_fields_imports(
    client: TestClient, project_id: str
) -> None:
    # An export file written before player access existed has no such keys.
    legacy = {
        "format_version": 1,
        "name": "Legacy",
        "entities": [
            {
                "id": "e1",
                "type": "npc",
                "title": "Old NPC",
                "fields": [{"key": "role", "field_type": "text", "value": "smith"}],
            }
        ],
        "edges": [],
    }
    imported = client.post("/api/projects/import", json=legacy).json()
    entity = client.get(f"/api/projects/{imported['id']}/entities").json()[0]
    assert entity["revealed_to_players"] is False
    assert entity["player_text"] is None
    assert entity["fields"][0]["visible_to_players"] is False
