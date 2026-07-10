from fastapi.testclient import TestClient


def _create_entity(client: TestClient, project_id: str, title: str = "A") -> str:
    resp = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": title}
    )
    entity_id = resp.json()["id"]
    assert isinstance(entity_id, str)
    return entity_id


def test_upload_creates_row_and_servable_file(
    client: TestClient, project_id: str
) -> None:
    entity_id = _create_entity(client, project_id)

    resp = client.post(
        f"/api/entities/{entity_id}/attachments",
        files={"file": ("portrait.png", b"fake-bytes", "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["entity_id"] == entity_id
    assert body["original_filename"] == "portrait.png"

    served = client.get(body["url"])
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")


def test_upload_for_missing_entity_is_404(client: TestClient) -> None:
    resp = client.post(
        "/api/entities/missing/attachments",
        files={"file": ("a.png", b"x", "image/png")},
    )
    assert resp.status_code == 404


def test_delete_attachment_removes_row_and_file(
    client: TestClient, project_id: str
) -> None:
    entity_id = _create_entity(client, project_id)
    upload = client.post(
        f"/api/entities/{entity_id}/attachments",
        files={"file": ("a.png", b"x", "image/png")},
    ).json()

    assert client.delete(f"/api/attachments/{upload['id']}").status_code == 204
    assert client.get(f"/api/entities/{entity_id}/attachments").json() == []
    assert client.get(upload["url"]).status_code == 404
