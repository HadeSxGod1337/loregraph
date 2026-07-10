from fastapi.testclient import TestClient


def _create_entity(client: TestClient, project_id: str, title: str) -> str:
    resp = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": title}
    )
    entity_id = resp.json()["id"]
    assert isinstance(entity_id, str)
    return entity_id


def test_create_edge_between_existing_entities(
    client: TestClient, project_id: str
) -> None:
    a, b = (
        _create_entity(client, project_id, "A"),
        _create_entity(client, project_id, "B"),
    )

    resp = client.post(
        f"/api/projects/{project_id}/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source_entity_id"] == a
    assert body["target_entity_id"] == b
    assert body["project_id"] == project_id


def test_create_edge_with_missing_entity_is_422(
    client: TestClient, project_id: str
) -> None:
    a = _create_entity(client, project_id, "A")

    resp = client.post(
        f"/api/projects/{project_id}/edges",
        json={"source_entity_id": a, "target_entity_id": "missing", "type": "ally_of"},
    )
    assert resp.status_code == 422


def test_create_edge_across_projects_is_422(
    client: TestClient, project_id: str
) -> None:
    other_project = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    a = _create_entity(client, project_id, "A")
    b = _create_entity(client, other_project, "B")

    resp = client.post(
        f"/api/projects/{project_id}/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    )
    assert resp.status_code == 422


def test_list_edges_by_entity_matches_source_or_target(
    client: TestClient, project_id: str
) -> None:
    a, b, c = (_create_entity(client, project_id, n) for n in ("A", "B", "C"))
    client.post(
        f"/api/projects/{project_id}/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    )
    client.post(
        f"/api/projects/{project_id}/edges",
        json={"source_entity_id": c, "target_entity_id": a, "type": "family_of"},
    )

    resp = client.get(f"/api/projects/{project_id}/edges", params={"entity_id": a})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_does_not_include_other_projects_edges(
    client: TestClient, project_id: str
) -> None:
    other_project = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    oa, ob = (
        _create_entity(client, other_project, "A"),
        _create_entity(client, other_project, "B"),
    )
    client.post(
        f"/api/projects/{other_project}/edges",
        json={"source_entity_id": oa, "target_entity_id": ob, "type": "ally_of"},
    )

    resp = client.get(f"/api/projects/{project_id}/edges")
    assert resp.status_code == 200
    assert resp.json() == []


def test_update_edge_changes_type_and_label(
    client: TestClient, project_id: str
) -> None:
    a, b = (
        _create_entity(client, project_id, "A"),
        _create_entity(client, project_id, "B"),
    )
    edge = client.post(
        f"/api/projects/{project_id}/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    ).json()

    resp = client.put(
        f"/api/projects/{project_id}/edges/{edge['id']}",
        json={"type": "family_of", "label": "sister"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "family_of"
    assert body["label"] == "sister"


def test_update_unknown_edge_is_404(client: TestClient, project_id: str) -> None:
    resp = client.put(
        f"/api/projects/{project_id}/edges/missing", json={"type": "ally_of"}
    )
    assert resp.status_code == 404


def test_update_edge_from_another_project_is_404(
    client: TestClient, project_id: str
) -> None:
    other_project = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    oa, ob = (
        _create_entity(client, other_project, "A"),
        _create_entity(client, other_project, "B"),
    )
    edge = client.post(
        f"/api/projects/{other_project}/edges",
        json={"source_entity_id": oa, "target_entity_id": ob, "type": "ally_of"},
    ).json()

    resp = client.put(
        f"/api/projects/{project_id}/edges/{edge['id']}", json={"type": "family_of"}
    )
    assert resp.status_code == 404


def test_delete_edge(client: TestClient, project_id: str) -> None:
    a, b = (
        _create_entity(client, project_id, "A"),
        _create_entity(client, project_id, "B"),
    )
    edge = client.post(
        f"/api/projects/{project_id}/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    ).json()

    assert (
        client.delete(f"/api/projects/{project_id}/edges/{edge['id']}").status_code
        == 204
    )
    assert (
        client.get(f"/api/projects/{project_id}/edges", params={"entity_id": a}).json()
        == []
    )


def test_delete_entity_cascades_edges(client: TestClient, project_id: str) -> None:
    a, b = (
        _create_entity(client, project_id, "A"),
        _create_entity(client, project_id, "B"),
    )
    client.post(
        f"/api/projects/{project_id}/edges",
        json={"source_entity_id": a, "target_entity_id": b, "type": "ally_of"},
    )

    client.delete(f"/api/projects/{project_id}/entities/{a}")

    assert (
        client.get(f"/api/projects/{project_id}/edges", params={"entity_id": b}).json()
        == []
    )
