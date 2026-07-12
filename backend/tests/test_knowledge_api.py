import time
from typing import Any

from fastapi.testclient import TestClient

from loregraph.api.routers.knowledge import MAX_KNOWLEDGE_FILE_BYTES

_POLL_ATTEMPTS = 50
_POLL_INTERVAL_SECONDS = 0.05


def _wait_for_status(
    client: TestClient, project_id: str, source_id: str
) -> dict[str, Any]:
    """BackgroundTasks run after the response is sent, not synchronously
    inside client.post() — poll the list endpoint like the real UI does
    (see hooks/useKnowledge.ts) instead of assuming completion."""
    for _ in range(_POLL_ATTEMPTS):
        sources: list[dict[str, Any]] = client.get(
            f"/api/projects/{project_id}/knowledge"
        ).json()
        source = next(s for s in sources if s["id"] == source_id)
        if source["status"] != "pending":
            return source
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise AssertionError(f"knowledge source {source_id} never left 'pending' status")


def test_upload_list_and_delete_knowledge_source(
    client: TestClient, project_id: str
) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/knowledge",
        files={"file": ("setting.txt", b"A short setting bible.", "text/plain")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["original_filename"] == "setting.txt"
    assert body["project_id"] == project_id

    # The fixture's Settings disable embeddings, so ingestion takes the
    # "ready, not searchable" degrade path (see services/knowledge_ingest.py).
    settled = _wait_for_status(client, project_id, body["id"])
    assert settled["status"] == "ready"
    assert settled["chunk_count"] == 0

    listed = client.get(f"/api/projects/{project_id}/knowledge").json()
    assert [s["id"] for s in listed] == [body["id"]]

    assert client.delete(f"/api/knowledge/{body['id']}").status_code == 204
    assert client.get(f"/api/projects/{project_id}/knowledge").json() == []


def test_upload_for_missing_project_is_404(client: TestClient) -> None:
    resp = client.post(
        "/api/projects/missing/knowledge",
        files={"file": ("a.txt", b"x", "text/plain")},
    )
    assert resp.status_code == 404


def test_upload_oversized_file_is_422(client: TestClient, project_id: str) -> None:
    oversized = b"x" * (MAX_KNOWLEDGE_FILE_BYTES + 1)
    resp = client.post(
        f"/api/projects/{project_id}/knowledge",
        files={"file": ("big.txt", oversized, "text/plain")},
    )
    assert resp.status_code == 422


def test_delete_unknown_source_is_404(client: TestClient) -> None:
    assert client.delete("/api/knowledge/missing").status_code == 404


def test_upload_with_embeddings_disabled_stores_file_regardless_of_type(
    client: TestClient, project_id: str
) -> None:
    """With embeddings disabled, ingest_source short-circuits before
    extract_text runs (see test_knowledge_ingest.py for the actual
    unsupported-type failure path, exercised against a real KnowledgeIndex)
    — the file is still stored and listable even for a type the parser
    doesn't support."""
    resp = client.post(
        f"/api/projects/{project_id}/knowledge",
        files={"file": ("art.png", b"not-really-an-image", "image/png")},
    )
    assert resp.status_code == 201
    settled = _wait_for_status(client, project_id, resp.json()["id"])
    assert settled["status"] == "ready"
