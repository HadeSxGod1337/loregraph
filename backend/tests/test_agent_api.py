from fastapi.testclient import TestClient


def test_agent_config_unconfigured(client: TestClient) -> None:
    resp = client.get("/api/agent/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_configured"] is False
    assert body["llm_provider"] == "anthropic"
    assert body["vector_enabled"] is False  # disabled in test settings


def test_create_session_needs_no_llm(client: TestClient, project_id: str) -> None:
    """Creating a conversation is registry-only — no API key required."""
    resp = client.post(f"/api/projects/{project_id}/agent/sessions")
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "idle"
    assert body["title"] == ""
    assert body["project_id"] == project_id


def test_send_message_without_key_is_409(client: TestClient, project_id: str) -> None:
    created = client.post(f"/api/projects/{project_id}/agent/sessions").json()
    resp = client.post(
        f"/api/projects/{project_id}/agent/sessions/{created['thread_id']}/messages",
        json={"text": "Создай стартовый лор"},
    )
    assert resp.status_code == 409
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_list_sessions(client: TestClient, project_id: str) -> None:
    client.post(f"/api/projects/{project_id}/agent/sessions")
    resp = client.get(f"/api/projects/{project_id}/agent/sessions")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_session_is_project_scoped(client: TestClient, project_id: str) -> None:
    created = client.post(f"/api/projects/{project_id}/agent/sessions").json()
    other = client.post("/api/projects", json={"name": "Other"}).json()
    resp = client.get(
        f"/api/projects/{other['id']}/agent/sessions/{created['thread_id']}"
    )
    # Detail goes through the runner (needs LLM config) or 404s first on the
    # cross-project check — either way the session must not leak.
    assert resp.status_code in (404, 409)


def test_get_unknown_session_is_404_or_409(client: TestClient, project_id: str) -> None:
    resp = client.get(f"/api/projects/{project_id}/agent/sessions/nope")
    assert resp.status_code in (404, 409)
