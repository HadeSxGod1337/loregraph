from typing import Any

from fastapi.testclient import TestClient


def _upload_ready_source(client: TestClient, project_id: str) -> dict[str, Any]:
    """Uploads via the real endpoint (embeddings disabled in test settings,
    so ingestion runs synchronously enough that the BackgroundTask has
    finished by the time we read it back through list)."""
    resp = client.post(
        f"/api/projects/{project_id}/knowledge",
        files={
            "file": ("lore.txt", b"Some lore text about a blacksmith.", "text/plain")
        },
    )
    assert resp.status_code == 201
    source_id = resp.json()["id"]
    # embeddings disabled -> ingest_source degrades straight to "ready"
    # synchronously enough within the same BackgroundTask/test client call.
    sources = client.get(f"/api/projects/{project_id}/knowledge").json()
    return next(s for s in sources if s["id"] == source_id)


def test_start_import_for_unknown_project_is_404(client: TestClient) -> None:
    resp = client.post(
        "/api/projects/does-not-exist/import-jobs", json={"source_id": "nope"}
    )
    assert resp.status_code == 404


def test_start_import_for_unknown_source_is_404(
    client: TestClient, project_id: str
) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/import-jobs", json={"source_id": "nope"}
    )
    assert resp.status_code == 404


def test_start_import_for_not_ready_source_is_409(
    client: TestClient, project_id: str
) -> None:
    # A source that failed ingestion (unsupported type) never reaches
    # "ready" — chunk_count stays 0 even if status were forced to ready.
    resp = client.post(
        f"/api/projects/{project_id}/knowledge",
        files={"file": ("art.png", b"not-an-image", "image/png")},
    )
    source_id = resp.json()["id"]
    start = client.post(
        f"/api/projects/{project_id}/import-jobs", json={"source_id": source_id}
    )
    assert start.status_code == 409


def test_start_import_without_llm_key_is_409_once_source_is_ready(
    client: TestClient, project_id: str
) -> None:
    source = _upload_ready_source(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/import-jobs", json={"source_id": source["id"]}
    )
    assert resp.status_code == 409
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_review_unknown_job_is_404(client: TestClient, project_id: str) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/import-jobs/nope/review",
        json={"action": "approve"},
    )
    assert resp.status_code == 404


def test_list_and_get_import_jobs_needs_no_llm(
    client: TestClient, project_id: str
) -> None:
    resp = client.get(f"/api/projects/{project_id}/import-jobs")
    assert resp.status_code == 200
    assert resp.json() == []
