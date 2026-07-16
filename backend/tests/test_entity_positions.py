from fastapi.testclient import TestClient


def _create_entity(client: TestClient, project_id: str, title: str = "A") -> str:
    resp = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": title}
    )
    entity_id = resp.json()["id"]
    assert isinstance(entity_id, str)
    return entity_id


def test_new_entity_has_null_position(client: TestClient, project_id: str) -> None:
    entity_id = _create_entity(client, project_id)
    resp = client.get(f"/api/projects/{project_id}/entities/{entity_id}")
    assert resp.json()["pos_x"] is None
    assert resp.json()["pos_y"] is None


def test_update_positions_reflects_on_get(client: TestClient, project_id: str) -> None:
    entity_a = _create_entity(client, project_id, "A")
    entity_b = _create_entity(client, project_id, "B")

    resp = client.put(
        f"/api/projects/{project_id}/entities/positions",
        json=[
            {"entity_id": entity_a, "pos_x": 12.5, "pos_y": -4.0},
            {"entity_id": entity_b, "pos_x": 100.0, "pos_y": 200.0},
        ],
    )
    assert resp.status_code == 200
    body = {e["id"]: e for e in resp.json()}
    assert body[entity_a]["pos_x"] == 12.5
    assert body[entity_a]["pos_y"] == -4.0
    assert body[entity_b]["pos_x"] == 100.0

    got = client.get(f"/api/projects/{project_id}/entities/{entity_a}")
    assert got.json()["pos_x"] == 12.5
    assert got.json()["pos_y"] == -4.0


def test_update_positions_unknown_entity_is_404(
    client: TestClient, project_id: str
) -> None:
    resp = client.put(
        f"/api/projects/{project_id}/entities/positions",
        json=[{"entity_id": "missing", "pos_x": 1.0, "pos_y": 2.0}],
    )
    assert resp.status_code == 404


def test_update_positions_rejects_entity_from_another_project(
    client: TestClient, project_id: str
) -> None:
    other_project = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    foreign_entity = _create_entity(client, other_project, "Foreign")

    resp = client.put(
        f"/api/projects/{project_id}/entities/positions",
        json=[{"entity_id": foreign_entity, "pos_x": 1.0, "pos_y": 2.0}],
    )
    assert resp.status_code == 404
