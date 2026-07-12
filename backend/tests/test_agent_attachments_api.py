import base64

from fastapi.testclient import TestClient

from loregraph.api.routers.agent import (
    MAX_CHAT_ATTACHMENT_BYTES,
    MAX_CHAT_ATTACHMENTS_PER_TURN,
)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _session(client: TestClient, project_id: str) -> str:
    created = client.post(f"/api/projects/{project_id}/agent/sessions").json()
    thread_id = created["thread_id"]
    assert isinstance(thread_id, str)
    return thread_id


def test_too_many_attachments_is_422_even_without_llm_key(
    client: TestClient, project_id: str
) -> None:
    """Regression: attachment validation is a Depends() guard declared
    before AgentRunnerDep specifically so it runs (and returns 422) even
    when no LLM key is configured — see api/routers/agent.py's guard-
    ordering comment. Without that ordering this would 409 instead."""
    thread_id = _session(client, project_id)
    attachments = [
        {
            "filename": f"a{i}.png",
            "content_type": "image/png",
            "data_base64": _b64(b"x"),
        }
        for i in range(MAX_CHAT_ATTACHMENTS_PER_TURN + 1)
    ]
    resp = client.post(
        f"/api/projects/{project_id}/agent/sessions/{thread_id}/messages",
        json={"text": "hi", "attachments": attachments},
    )
    assert resp.status_code == 422


def test_oversized_attachment_is_422_even_without_llm_key(
    client: TestClient, project_id: str
) -> None:
    thread_id = _session(client, project_id)
    oversized_b64 = _b64(b"x" * (MAX_CHAT_ATTACHMENT_BYTES + 1))
    resp = client.post(
        f"/api/projects/{project_id}/agent/sessions/{thread_id}/messages",
        json={
            "text": "hi",
            "attachments": [
                {
                    "filename": "big.png",
                    "content_type": "image/png",
                    "data_base64": oversized_b64,
                }
            ],
        },
    )
    assert resp.status_code == 422


def test_unsupported_attachment_type_is_422_even_without_llm_key(
    client: TestClient, project_id: str
) -> None:
    thread_id = _session(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/agent/sessions/{thread_id}/messages",
        json={
            "text": "hi",
            "attachments": [
                {
                    "filename": "video.mp4",
                    "content_type": "video/mp4",
                    "data_base64": _b64(b"x"),
                }
            ],
        },
    )
    assert resp.status_code == 422


def test_message_without_attachments_still_hits_409_without_llm_key(
    client: TestClient, project_id: str
) -> None:
    """Sanity check that the new guard doesn't shadow the pre-existing
    "no LLM configured" behavior for ordinary text-only messages."""
    thread_id = _session(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/agent/sessions/{thread_id}/messages",
        json={"text": "hi"},
    )
    assert resp.status_code == 409
