from fastapi import FastAPI
from fastapi.testclient import TestClient


def _upload(client: TestClient, project_id: str) -> tuple[str, str]:
    entity = client.post(
        f"/api/projects/{project_id}/entities",
        json={"type": "npc", "title": "Mira"},
    ).json()
    attachment = client.post(
        f"/api/entities/{entity['id']}/attachments",
        files={"file": ("portrait.txt", b"hello", "text/plain")},
    ).json()
    return entity["id"], attachment["url"]


def test_master_can_fetch_attachment(client: TestClient, project_id: str) -> None:
    _entity_id, url = _upload(client, project_id)
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.content == b"hello"


def test_missing_file_is_404(client: TestClient, project_id: str) -> None:
    entity_id, _url = _upload(client, project_id)
    assert client.get(f"/files/{entity_id}/nope.txt").status_code == 404


def test_path_traversal_is_rejected(client: TestClient, project_id: str) -> None:
    entity_id, _url = _upload(client, project_id)
    # Encoded traversal must not escape the attachments directory.
    resp = client.get(
        f"/files/{entity_id}/..%2f..%2fcampaign.sqlite3",
        follow_redirects=False,
    )
    assert resp.status_code == 404


def test_non_loopback_without_token_is_rejected(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    _entity_id, url = _upload(client, project_id)
    with TestClient(app, client=("192.168.1.50", 1)) as lan:
        assert lan.get(url).status_code == 401
