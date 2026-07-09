from fastapi.testclient import TestClient


def _create_entity(client: TestClient, title: str) -> str:
    resp = client.post("/api/entities", json={"type": "npc", "title": title})
    entity_id = resp.json()["id"]
    assert isinstance(entity_id, str)
    return entity_id


def test_create_edge_between_existing_entities(client: TestClient) -> None:
    a, b = _create_entity(client, "A"), _create_entity(client, "B")

    resp = client.post(
        "/api/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source_entity_id"] == a
    assert body["target_entity_id"] == b


def test_create_edge_with_missing_entity_is_422(client: TestClient) -> None:
    a = _create_entity(client, "A")

    resp = client.post(
        "/api/edges",
        json={"source_entity_id": a, "target_entity_id": "missing", "type": "ally_of"},
    )
    assert resp.status_code == 422


def test_list_edges_by_entity_matches_source_or_target(client: TestClient) -> None:
    a, b, c = (_create_entity(client, n) for n in ("A", "B", "C"))
    client.post(
        "/api/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    )
    client.post(
        "/api/edges",
        json={"source_entity_id": c, "target_entity_id": a, "type": "family_of"},
    )

    resp = client.get("/api/edges", params={"entity_id": a})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_update_edge_changes_type_and_label(client: TestClient) -> None:
    a, b = _create_entity(client, "A"), _create_entity(client, "B")
    edge = client.post(
        "/api/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    ).json()

    resp = client.put(
        f"/api/edges/{edge['id']}", json={"type": "family_of", "label": "sister"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "family_of"
    assert body["label"] == "sister"


def test_update_unknown_edge_is_404(client: TestClient) -> None:
    resp = client.put("/api/edges/missing", json={"type": "ally_of"})
    assert resp.status_code == 404


def test_delete_edge(client: TestClient) -> None:
    a, b = _create_entity(client, "A"), _create_entity(client, "B")
    edge = client.post(
        "/api/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    ).json()

    assert client.delete(f"/api/edges/{edge['id']}").status_code == 204
    assert client.get("/api/edges", params={"entity_id": a}).json() == []


def test_delete_entity_cascades_edges(client: TestClient) -> None:
    a, b = _create_entity(client, "A"), _create_entity(client, "B")
    client.post(
        "/api/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    )

    client.delete(f"/api/entities/{a}")

    assert client.get("/api/edges", params={"entity_id": b}).json() == []
