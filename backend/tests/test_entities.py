from fastapi.testclient import TestClient


def test_create_entity_defaults_fields_empty(client: TestClient) -> None:
    resp = client.post("/api/entities", json={"type": "npc", "title": "Mira"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["fields"] == []
    assert body["type"] == "npc"
    assert body["title"] == "Mira"
    assert body["icon"] is None


def test_rich_text_field_accepts_prosemirror_doc(client: TestClient) -> None:
    doc = {"type": "doc", "content": [{"type": "paragraph"}]}
    resp = client.post(
        "/api/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [{"key": "backstory", "field_type": "rich_text", "value": doc}],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["fields"][0]["value"] == doc


def test_rich_text_field_rejects_plain_string(client: TestClient) -> None:
    resp = client.post(
        "/api/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [{"key": "backstory", "field_type": "rich_text", "value": "hi"}],
        },
    )
    assert resp.status_code == 422


def test_rich_text_field_rejects_dict_without_type_key(client: TestClient) -> None:
    resp = client.post(
        "/api/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [
                {"key": "backstory", "field_type": "rich_text", "value": {"foo": "bar"}}
            ],
        },
    )
    assert resp.status_code == 422


def test_create_and_get_roundtrips_field_order(client: TestClient) -> None:
    fields = [
        {"key": "role", "field_type": "text", "value": "Blacksmith"},
        {"key": "level", "field_type": "number", "value": 6},
        {"key": "tags", "field_type": "tag", "value": ["ally", "gruff"]},
    ]
    resp = client.post(
        "/api/entities", json={"type": "npc", "title": "Mira", "fields": fields}
    )
    entity_id = resp.json()["id"]

    got = client.get(f"/api/entities/{entity_id}")
    assert got.status_code == 200
    assert [f["key"] for f in got.json()["fields"]] == ["role", "level", "tags"]


def test_get_unknown_entity_404(client: TestClient) -> None:
    resp = client.get("/api/entities/does-not-exist")
    assert resp.status_code == 404


def test_list_filtered_by_type(client: TestClient) -> None:
    client.post("/api/entities", json={"type": "npc", "title": "A"})
    client.post("/api/entities", json={"type": "location", "title": "B"})

    resp = client.get("/api/entities", params={"type": "npc"})
    assert resp.status_code == 200
    assert {e["type"] for e in resp.json()} == {"npc"}


def test_update_replaces_fields_wholesale(client: TestClient) -> None:
    created = client.post(
        "/api/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [{"key": "role", "field_type": "text", "value": "Smith"}],
        },
    ).json()

    updated = client.put(
        f"/api/entities/{created['id']}",
        json={"type": "npc", "title": "Mira Kuznets", "fields": []},
    )
    assert updated.status_code == 200
    assert updated.json()["fields"] == []
    assert updated.json()["title"] == "Mira Kuznets"


def test_delete_then_get_is_404(client: TestClient) -> None:
    created = client.post("/api/entities", json={"type": "npc", "title": "Temp"}).json()

    assert client.delete(f"/api/entities/{created['id']}").status_code == 204
    assert client.get(f"/api/entities/{created['id']}").status_code == 404
