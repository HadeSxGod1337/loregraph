from fastapi.testclient import TestClient


def test_create_and_get_project(client: TestClient) -> None:
    resp = client.post(
        "/api/projects", json={"name": "Curse of Strahd", "description": "Barovia"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Curse of Strahd"
    assert body["description"] == "Barovia"

    got = client.get(f"/api/projects/{body['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "Curse of Strahd"


def test_list_projects_includes_seeded_demo(client: TestClient) -> None:
    # main.py auto-seeds "Loregraph Demo" on first startup against an empty DB.
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert "Loregraph Demo" in {p["name"] for p in resp.json()}


def test_update_project(client: TestClient, project_id: str) -> None:
    resp = client.put(
        f"/api/projects/{project_id}", json={"name": "Renamed", "description": None}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


def test_get_unknown_project_404(client: TestClient) -> None:
    assert client.get("/api/projects/missing").status_code == 404


def test_project_agent_instructions_round_trip(client: TestClient) -> None:
    created = client.post(
        "/api/projects",
        json={"name": "Styled", "agent_instructions": "Write NPCs in second person."},
    ).json()
    assert created["agent_instructions"] == "Write NPCs in second person."

    fetched = client.get(f"/api/projects/{created['id']}").json()
    assert fetched["agent_instructions"] == "Write NPCs in second person."

    updated = client.put(
        f"/api/projects/{created['id']}",
        json={"name": "Styled", "description": None, "agent_instructions": "Be terse."},
    ).json()
    assert updated["agent_instructions"] == "Be terse."


def test_delete_project_cascades_entities(client: TestClient, project_id: str) -> None:
    entity_id = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "Mira"}
    ).json()["id"]

    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    # the entity's project is gone — it's unreachable via any project scope
    other = client.post("/api/projects", json={"name": "Scratch"}).json()["id"]
    assert client.get(f"/api/projects/{other}/entities/{entity_id}").status_code == 404


def test_export_import_round_trip(client: TestClient, project_id: str) -> None:
    a = client.post(
        f"/api/projects/{project_id}/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [{"key": "role", "field_type": "text", "value": "Smith"}],
        },
    ).json()["id"]
    b = client.post(
        f"/api/projects/{project_id}/entities",
        json={"type": "location", "title": "Forge"},
    ).json()["id"]
    client.post(
        f"/api/projects/{project_id}/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "works_at"},
    )

    export = client.get(f"/api/projects/{project_id}/export")
    assert export.status_code == 200
    exported = export.json()
    assert exported["format_version"] == 1
    assert len(exported["entities"]) == 2
    assert len(exported["edges"]) == 1

    imported = client.post("/api/projects/import", json=exported)
    assert imported.status_code == 201
    new_project_id = imported.json()["id"]
    assert new_project_id != project_id

    new_entities = client.get(f"/api/projects/{new_project_id}/entities").json()
    assert {e["title"] for e in new_entities} == {"Mira", "Forge"}
    # ids were remapped, not reused, on import
    assert {e["id"] for e in new_entities}.isdisjoint({a, b})

    new_edges = client.get(f"/api/projects/{new_project_id}/edges").json()
    assert len(new_edges) == 1
    assert new_edges[0]["type"] == "works_at"


def test_export_import_round_trip_with_icon(
    client: TestClient, project_id: str
) -> None:
    entity_id = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "Mira"}
    ).json()["id"]
    attachment = client.post(
        f"/api/entities/{entity_id}/attachments",
        files={"file": ("portrait.png", b"fake-bytes", "image/png")},
    ).json()
    client.put(
        f"/api/projects/{project_id}/entities/{entity_id}/icon",
        json={"attachment_id": attachment["id"]},
    )

    exported = client.get(f"/api/projects/{project_id}/export").json()
    assert len(exported["attachments"]) == 1

    imported = client.post("/api/projects/import", json=exported)
    new_project_id = imported.json()["id"]
    new_entity = client.get(f"/api/projects/{new_project_id}/entities").json()[0]

    assert new_entity["icon"] is not None
    assert new_entity["icon"]["attachment_id"] != attachment["id"]
    served = client.get(new_entity["icon"]["url"])
    assert served.status_code == 200
    assert served.content == b"fake-bytes"


def test_import_rejects_unsupported_format_version(client: TestClient) -> None:
    resp = client.post(
        "/api/projects/import",
        json={
            "format_version": 999,
            "name": "Broken",
            "entities": [],
            "edges": [],
            "attachments": [],
        },
    )
    assert resp.status_code == 422
