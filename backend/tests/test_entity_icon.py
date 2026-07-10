from fastapi.testclient import TestClient


def _create_entity(client: TestClient, project_id: str, title: str = "A") -> str:
    resp = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": title}
    )
    entity_id = resp.json()["id"]
    assert isinstance(entity_id, str)
    return entity_id


def _upload_attachment(client: TestClient, entity_id: str) -> str:
    resp = client.post(
        f"/api/entities/{entity_id}/attachments",
        files={"file": ("portrait.png", b"fake-bytes", "image/png")},
    )
    attachment_id = resp.json()["id"]
    assert isinstance(attachment_id, str)
    return attachment_id


def test_set_icon_reflects_on_get(client: TestClient, project_id: str) -> None:
    entity_id = _create_entity(client, project_id)
    attachment_id = _upload_attachment(client, entity_id)

    resp = client.put(
        f"/api/projects/{project_id}/entities/{entity_id}/icon",
        json={"attachment_id": attachment_id},
    )
    assert resp.status_code == 200
    assert resp.json()["icon"]["attachment_id"] == attachment_id

    got = client.get(f"/api/projects/{project_id}/entities/{entity_id}")
    assert got.json()["icon"]["attachment_id"] == attachment_id


def test_clear_icon(client: TestClient, project_id: str) -> None:
    entity_id = _create_entity(client, project_id)
    attachment_id = _upload_attachment(client, entity_id)
    client.put(
        f"/api/projects/{project_id}/entities/{entity_id}/icon",
        json={"attachment_id": attachment_id},
    )

    resp = client.delete(f"/api/projects/{project_id}/entities/{entity_id}/icon")
    assert resp.status_code == 200
    assert resp.json()["icon"] is None
    assert (
        client.get(f"/api/projects/{project_id}/entities/{entity_id}").json()["icon"]
        is None
    )


def test_set_icon_to_another_entitys_attachment_is_422(
    client: TestClient, project_id: str
) -> None:
    entity_a = _create_entity(client, project_id, "A")
    entity_b = _create_entity(client, project_id, "B")
    attachment_on_b = _upload_attachment(client, entity_b)

    resp = client.put(
        f"/api/projects/{project_id}/entities/{entity_a}/icon",
        json={"attachment_id": attachment_on_b},
    )
    assert resp.status_code == 422


def test_set_icon_unknown_attachment_is_404(
    client: TestClient, project_id: str
) -> None:
    entity_id = _create_entity(client, project_id)
    resp = client.put(
        f"/api/projects/{project_id}/entities/{entity_id}/icon",
        json={"attachment_id": "missing"},
    )
    assert resp.status_code == 404


def test_deleting_icon_attachment_clears_entity_icon(
    client: TestClient, project_id: str
) -> None:
    entity_id = _create_entity(client, project_id)
    attachment_id = _upload_attachment(client, entity_id)
    client.put(
        f"/api/projects/{project_id}/entities/{entity_id}/icon",
        json={"attachment_id": attachment_id},
    )

    assert client.delete(f"/api/attachments/{attachment_id}").status_code == 204

    assert (
        client.get(f"/api/projects/{project_id}/entities/{entity_id}").json()["icon"]
        is None
    )
