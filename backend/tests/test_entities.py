from fastapi.testclient import TestClient


def test_create_entity_defaults_fields_empty(
    client: TestClient, project_id: str
) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "Mira"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["fields"] == []
    assert body["type"] == "npc"
    assert body["title"] == "Mira"
    assert body["icon"] is None
    assert body["project_id"] == project_id


def test_rich_text_field_accepts_prosemirror_doc(
    client: TestClient, project_id: str
) -> None:
    doc = {"type": "doc", "content": [{"type": "paragraph"}]}
    resp = client.post(
        f"/api/projects/{project_id}/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [{"key": "backstory", "field_type": "rich_text", "value": doc}],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["fields"][0]["value"] == doc


def test_rich_text_field_rejects_plain_string(
    client: TestClient, project_id: str
) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [{"key": "backstory", "field_type": "rich_text", "value": "hi"}],
        },
    )
    assert resp.status_code == 422


def test_rich_text_field_rejects_dict_without_type_key(
    client: TestClient, project_id: str
) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [
                {"key": "backstory", "field_type": "rich_text", "value": {"foo": "bar"}}
            ],
        },
    )
    assert resp.status_code == 422


def test_create_and_get_roundtrips_field_order(
    client: TestClient, project_id: str
) -> None:
    fields = [
        {"key": "role", "field_type": "text", "value": "Blacksmith"},
        {"key": "level", "field_type": "number", "value": 6},
        {"key": "tags", "field_type": "tag", "value": ["ally", "gruff"]},
    ]
    resp = client.post(
        f"/api/projects/{project_id}/entities",
        json={"type": "npc", "title": "Mira", "fields": fields},
    )
    entity_id = resp.json()["id"]

    got = client.get(f"/api/projects/{project_id}/entities/{entity_id}")
    assert got.status_code == 200
    assert [f["key"] for f in got.json()["fields"]] == ["role", "level", "tags"]


def test_get_unknown_entity_404(client: TestClient, project_id: str) -> None:
    resp = client.get(f"/api/projects/{project_id}/entities/does-not-exist")
    assert resp.status_code == 404


def test_get_entity_from_another_project_is_404(
    client: TestClient, project_id: str
) -> None:
    other_project = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    entity_id = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "Mira"}
    ).json()["id"]

    resp = client.get(f"/api/projects/{other_project}/entities/{entity_id}")
    assert resp.status_code == 404


def test_list_filtered_by_type(client: TestClient, project_id: str) -> None:
    client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "A"}
    )
    client.post(
        f"/api/projects/{project_id}/entities", json={"type": "location", "title": "B"}
    )

    resp = client.get(f"/api/projects/{project_id}/entities", params={"type": "npc"})
    assert resp.status_code == 200
    assert {e["type"] for e in resp.json()} == {"npc"}


def test_list_does_not_include_other_projects_entities(
    client: TestClient, project_id: str
) -> None:
    other_project = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    client.post(
        f"/api/projects/{other_project}/entities",
        json={"type": "npc", "title": "Elsewhere"},
    )
    client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "Here"}
    )

    resp = client.get(f"/api/projects/{project_id}/entities")
    assert [e["title"] for e in resp.json()] == ["Here"]


def test_update_replaces_fields_wholesale(client: TestClient, project_id: str) -> None:
    created = client.post(
        f"/api/projects/{project_id}/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [{"key": "role", "field_type": "text", "value": "Smith"}],
        },
    ).json()

    updated = client.put(
        f"/api/projects/{project_id}/entities/{created['id']}",
        json={"type": "npc", "title": "Mira Kuznets", "fields": []},
    )
    assert updated.status_code == 200
    assert updated.json()["fields"] == []
    assert updated.json()["title"] == "Mira Kuznets"


def test_delete_then_get_is_404(client: TestClient, project_id: str) -> None:
    created = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "Temp"}
    ).json()

    assert (
        client.delete(
            f"/api/projects/{project_id}/entities/{created['id']}"
        ).status_code
        == 204
    )
    assert (
        client.get(f"/api/projects/{project_id}/entities/{created['id']}").status_code
        == 404
    )
