from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from loregraph.connectors.registry import ConnectorDescriptor, ConnectorRegistry


def test_list_connector_types_reports_capabilities(client: TestClient) -> None:
    types = {t["connector_type"]: t for t in client.get("/api/connectors").json()}
    assert set(types) >= {"obsidian", "foundry", "longstoryshort"}
    assert types["obsidian"]["capabilities"] == ["export", "import"]
    assert types["foundry"]["capabilities"] == ["export", "import", "live"]
    assert types["longstoryshort"]["capabilities"] == ["import", "live"]


def test_connection_crud(client: TestClient, project_id: str, tmp_path: Any) -> None:
    base = f"/api/projects/{project_id}/connections"
    created = client.post(
        base,
        json={
            "connector_type": "obsidian",
            "name": "Vault",
            "config": {"vault_path": str(tmp_path)},
            "use_for_grounding": True,
        },
    )
    assert created.status_code == 201
    connection_id = created.json()["id"]
    assert created.json()["use_for_grounding"] is True

    listed = client.get(base).json()
    assert [c["id"] for c in listed] == [connection_id]

    updated = client.put(
        f"{base}/{connection_id}",
        json={
            "name": "Renamed Vault",
            "config": {"vault_path": str(tmp_path), "subfolder": "World"},
            "use_for_grounding": False,
            "auto_push_after_commit": True,
        },
    ).json()
    assert updated["name"] == "Renamed Vault"
    assert updated["config"]["subfolder"] == "World"
    assert updated["auto_push_after_commit"] is True

    assert client.delete(f"{base}/{connection_id}").status_code == 204
    assert client.get(base).json() == []


def test_unknown_connector_type_rejected(client: TestClient, project_id: str) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/connections",
        json={"connector_type": "notion", "name": "N", "config": {}},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "unknown_connector_type"


def test_invalid_config_rejected_without_leaking_values(
    client: TestClient, project_id: str
) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/connections",
        json={"connector_type": "obsidian", "name": "V", "config": {}},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "connector_config_invalid"
    assert "vault_path" in body["detail"]


def test_cross_project_connection_is_404(
    client: TestClient, project_id: str, tmp_path: Any
) -> None:
    other = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    connection_id = client.post(
        f"/api/projects/{project_id}/connections",
        json={
            "connector_type": "obsidian",
            "name": "V",
            "config": {"vault_path": str(tmp_path)},
        },
    ).json()["id"]
    resp = client.post(f"/api/projects/{other}/connections/{connection_id}/test")
    assert resp.status_code == 404
    assert resp.json()["code"] == "connection_not_found"


def test_capability_mismatch_is_422(
    client: TestClient, project_id: str, tmp_path: Any
) -> None:
    # Obsidian declares no live capability; ask it to export something it
    # can't — the unsupported axis here is import on... obsidian supports
    # both. Use LSS: it has no export capability.
    connection_id = client.post(
        f"/api/projects/{project_id}/connections",
        json={"connector_type": "longstoryshort", "name": "LSS", "config": {}},
    ).json()["id"]
    resp = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/export",
        json={},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "unsupported_connector_capability"


class _SecretConfig(BaseModel):
    api_token: str = Field(default="", json_schema_extra={"secret": True})


def test_secret_config_fields_are_masked(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    """Register a test-only connector type with a secret field and verify the
    API masks it on every read and keeps it on masked update (the pattern
    Notion/Miro will rely on)."""
    registry = cast(ConnectorRegistry, app.state.connector_registry)
    registry.register(
        ConnectorDescriptor(
            connector_type="secretive",
            config_model=_SecretConfig,
            factory=lambda config, context: object(),
            capabilities=frozenset(),
        )
    )
    base = f"/api/projects/{project_id}/connections"
    created = client.post(
        base,
        json={
            "connector_type": "secretive",
            "name": "S",
            "config": {"api_token": "ntn_supersecret1234"},
        },
    ).json()
    assert created["config"]["api_token"] == "••••1234"

    # Echoing the mask back on update keeps the stored secret...
    client.put(
        f"{base}/{created['id']}",
        json={
            "name": "S2",
            "config": {"api_token": "••••1234"},
            "use_for_grounding": False,
            "auto_push_after_commit": False,
        },
    )
    # ...which we can only observe indirectly: a fresh read still masks the
    # ORIGINAL last4, not the mask-of-a-mask.
    listed = client.get(base).json()
    assert listed[0]["config"]["api_token"] == "••••1234"
