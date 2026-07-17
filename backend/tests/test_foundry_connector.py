"""Foundry connector against a fake MCP client (the real bridge needs a live
Foundry — that's the manual E2E check, not CI's job)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

import loregraph.connectors.foundry.connector as foundry_module
from loregraph.exceptions import ConnectorUnavailableError


class FakeFoundryMcpClient:
    """Stands in for FoundryMcpClient: records calls, serves canned data."""

    instances: "list[FakeFoundryMcpClient]" = []
    fail_all = False

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[tuple[str, dict[str, Any]]] = []
        FakeFoundryMcpClient.instances.append(self)

    async def start(self) -> None:
        if FakeFoundryMcpClient.fail_all:
            raise ConnectorUnavailableError("Foundry", "bridge did not start")

    async def aclose(self) -> None:
        pass

    async def tool_names(self) -> frozenset[str]:
        return frozenset({"get-world-info", "create-quest-journal"})

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        match name:
            case "get-world-info":
                return {"title": "Barovia", "system": "dnd5e"}
            case "create-quest-journal":
                return {"id": f"journal-for-{arguments.get('title', '')}"}
            case "update-quest-journal":
                return {"ok": True}
            case "list-characters":
                return {
                    "characters": [
                        {"id": "actor-1", "name": "Strahd"},
                        {"id": "actor-2", "name": "Ireena"},
                    ]
                }
            case "get-character":
                return {
                    "name": arguments.get("characterName"),
                    "class": "Vampire",
                    "level": 15,
                    "biography": "Lord of Barovia.",
                }
            case "search-journals":
                return [{"name": "Session 3 notes", "content": "The party..."}]
            case _:
                return {}


@pytest.fixture(autouse=True)
def fake_mcp(monkeypatch: pytest.MonkeyPatch) -> type[FakeFoundryMcpClient]:
    FakeFoundryMcpClient.instances = []
    FakeFoundryMcpClient.fail_all = False
    monkeypatch.setattr(foundry_module, "FoundryMcpClient", FakeFoundryMcpClient)
    return FakeFoundryMcpClient


def _make_connection(client: TestClient, project_id: str) -> str:
    resp = client.post(
        f"/api/projects/{project_id}/connections",
        json={
            "connector_type": "foundry",
            "name": "My Foundry",
            "config": {"mcp_server_path": "C:/bridge/dist/index.js"},
        },
    )
    assert resp.status_code == 201, resp.text
    connection_id = resp.json()["id"]
    assert isinstance(connection_id, str)
    return connection_id


def _create_entity(client: TestClient, project_id: str, title: str) -> str:
    resp = client.post(
        f"/api/projects/{project_id}/entities",
        json={"type": "npc", "title": title},
    )
    entity_id = resp.json()["id"]
    assert isinstance(entity_id, str)
    return entity_id


def test_probe_returns_world_info(client: TestClient, project_id: str) -> None:
    connection_id = _make_connection(client, project_id)
    probe = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/test"
    ).json()
    assert probe["ok"] is True
    assert probe["info"]["title"] == "Barovia"


def test_probe_degrades_when_bridge_down(
    client: TestClient, project_id: str
) -> None:
    FakeFoundryMcpClient.fail_all = True
    connection_id = _make_connection(client, project_id)
    probe = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/test"
    ).json()
    assert probe["ok"] is False
    assert probe["detail_code"] == "foundry_unreachable"


def test_export_creates_then_updates_journals(
    client: TestClient, project_id: str
) -> None:
    _create_entity(client, project_id, "Strahd von Zarovich")
    connection_id = _make_connection(client, project_id)
    url = f"/api/projects/{project_id}/connections/{connection_id}/export"

    first = client.post(url, json={}).json()
    assert first["created"] == 1 and first["errors"] == []

    second = client.post(url, json={}).json()
    assert second["updated"] == 1 and second["created"] == 0

    calls = [c for i in FakeFoundryMcpClient.instances for c in i.calls]
    created = [c for c in calls if c[0] == "create-quest-journal"]
    updated = [c for c in calls if c[0] == "update-quest-journal"]
    assert len(created) == 1
    assert created[0][1]["title"] == "Strahd von Zarovich"
    assert len(updated) == 1
    # Provenance: the update targets the id the create returned.
    assert updated[0][1]["journalId"] == "journal-for-Strahd von Zarovich"


def test_import_pulls_actors_with_provenance_dedupe(
    client: TestClient, project_id: str
) -> None:
    connection_id = _make_connection(client, project_id)
    url = f"/api/projects/{project_id}/connections/{connection_id}/import"

    first = client.post(url, json={"payload": {}}).json()
    assert first["created"] == 2 and first["errors"] == []

    entities = client.get(f"/api/projects/{project_id}/entities").json()
    strahd = next(e for e in entities if e["title"] == "Strahd")
    by_key = {f["key"]: f for f in strahd["fields"]}
    assert by_key["tags"]["value"] == ["foundry-import"]
    assert by_key["class"]["value"] == "Vampire"
    assert by_key["level"]["value"] == 15

    # Second import: both actors already linked -> skipped, no duplicates.
    second = client.post(url, json={"payload": {}}).json()
    assert second["created"] == 0 and second["skipped"] == 2
    entities_after = client.get(f"/api/projects/{project_id}/entities").json()
    assert len(entities_after) == len(entities)


def test_export_while_bridge_down_is_502(
    client: TestClient, project_id: str
) -> None:
    _create_entity(client, project_id, "Ireena")
    FakeFoundryMcpClient.fail_all = True
    connection_id = _make_connection(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/export",
        json={},
    )
    assert resp.status_code == 502
    assert resp.json()["code"] == "connector_unavailable"
