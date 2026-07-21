"""Foundry connector against a fake MCP client (the real bridge needs a live
Foundry — that's the manual E2E check, not CI's job)."""

from typing import Any, ClassVar, cast

import pytest
from fastapi.testclient import TestClient

import loregraph.connectors.foundry.connector as foundry_module
from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.foundry.connector import FoundryConfig, FoundryConnector
from loregraph.exceptions import ConnectorUnavailableError


class FakeFoundryMcpClient:
    """Stands in for McpStdioClient: records calls, serves canned data."""

    instances: ClassVar[list["FakeFoundryMcpClient"]] = []
    fail_all = False
    world_item_count = 2

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
            case "list-journals" if "pageId" in arguments:
                # Real bridge shape (verified live): journalId+pageId returns
                # ONE page's FULL content as HTML — the migration path's
                # source, unlike search-journals' truncated snippet.
                return {
                    "success": True,
                    "mode": "page",
                    "journalId": arguments["journalId"],
                    "page": {
                        "id": arguments["pageId"],
                        "name": "Описание",
                        "type": "text",
                        "content": (
                            "<h3>1. Входной холл</h3><p>Главный вход и гардероб.</p>"
                        ),
                    },
                }
            case "list-journals":
                return {
                    "success": True,
                    "mode": "list",
                    "journals": [
                        {
                            "id": "journal-1",
                            "name": "SexSpace",
                            "pageCount": 1,
                            "pages": [{"id": "page-1", "name": "Описание"}],
                        }
                    ],
                    "total": 1,
                }
            case "get-character":
                # Real bridge shape (verified live against a running Foundry
                # world): keyed by "identifier" (name or id), not
                # "characterName"; stats nested under "stats", no
                # class/race/biography — the tool is deliberately
                # description-free ("optimized for minimal token usage").
                assert "identifier" in arguments
                return {
                    "name": arguments["identifier"],
                    "type": "npc",
                    "stats": {
                        "level": 15,
                        "armorClass": 16,
                        "challengeRating": 10,
                        "hitPoints": {"max": 144, "current": 144},
                    },
                    "items": [{"name": "Sunsword"}, {"name": "Holy Symbol"}],
                }
            case "search-journals":
                # Real bridge shape (verified live): keyed by "searchQuery",
                # not "query"; results are journal->matchedPages locators
                # with an HTML content snippet, not a flat list of records.
                assert "searchQuery" in arguments
                return {
                    "success": True,
                    "searchQuery": arguments["searchQuery"],
                    "results": [
                        {
                            "id": "journal-1",
                            "name": "Session 3 notes",
                            "pageCount": 2,
                            "matchedPages": [
                                {
                                    "pageId": "page-1",
                                    "pageName": "Lore",
                                    "contentSnippet": (
                                        '<p data-start="1">The party '
                                        "<strong>met Strahd</strong> at "
                                        "the castle gate.</p>"
                                    ),
                                }
                            ],
                        }
                    ],
                    "totalMatches": 1,
                }
            case "manage-world-items":
                # Real bridge shape (live-verified): action="list" returns
                # a flat item directory, no description text (there is no
                # "get one world item" action, only create/list/update/
                # add-to-actor).
                assert arguments.get("action") == "list"
                items = [
                    {
                        "id": "item-1",
                        "name": "Кольцо сопротивления",
                        "type": "loot",
                        "folderId": None,
                        "folderName": None,
                    },
                    {
                        "id": "item-2",
                        "name": "Молот",
                        "type": "weapon",
                        "folderId": "f1",
                        "folderName": "Оружие",
                    },
                ][: FakeFoundryMcpClient.world_item_count]
                missing = FakeFoundryMcpClient.world_item_count - len(items)
                if missing > 0:
                    items.extend(
                        {
                            "id": f"item-extra-{i}",
                            "name": f"Extra Item {i}",
                            "type": "loot",
                            "folderId": None,
                            "folderName": None,
                        }
                        for i in range(missing)
                    )
                return {"items": items, "total": len(items)}
            case _:
                return {}


@pytest.fixture(autouse=True)
def fake_mcp(monkeypatch: pytest.MonkeyPatch) -> type[FakeFoundryMcpClient]:
    FakeFoundryMcpClient.instances = []
    FakeFoundryMcpClient.fail_all = False
    FakeFoundryMcpClient.world_item_count = 2
    monkeypatch.setattr(foundry_module, "McpStdioClient", FakeFoundryMcpClient)
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


def test_probe_degrades_when_bridge_down(client: TestClient, project_id: str) -> None:
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
    assert by_key["level"]["value"] == 15
    assert by_key["ac"]["value"] == 16
    assert by_key["hp"]["value"] == 144
    assert by_key["cr"]["value"] == 10
    assert set(by_key["equipment"]["value"]) == {"Sunsword", "Holy Symbol"}

    # get-character must be looked up by the actor's Foundry id (by-name
    # lookups are ambiguous when actors share a name), and the call uses
    # the real "identifier" argument the bridge actually validates.
    get_character_calls = [
        c
        for i in FakeFoundryMcpClient.instances
        for c in i.calls
        if c[0] == "get-character"
    ]
    assert {c[1]["identifier"] for c in get_character_calls} == {"actor-1", "actor-2"}

    # Second import: both actors already linked -> skipped, no duplicates.
    second = client.post(url, json={"payload": {}}).json()
    assert second["created"] == 0 and second["skipped"] == 2
    entities_after = client.get(f"/api/projects/{project_id}/entities").json()
    assert len(entities_after) == len(entities)


def test_export_while_bridge_down_is_502(client: TestClient, project_id: str) -> None:
    _create_entity(client, project_id, "Ireena")
    FakeFoundryMcpClient.fail_all = True
    connection_id = _make_connection(client, project_id)
    resp = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/export",
        json={},
    )
    assert resp.status_code == 502
    assert resp.json()["code"] == "connector_unavailable"


def _make_connector() -> FoundryConnector:
    """Constructs a FoundryConnector directly against the fake bridge, for
    testing FoundryConnector.query() (the LiveSource protocol method the
    assistant's query_external_source chat tool calls) without the full
    HTTP/DB stack the other tests in this file use. No runtime
    (runtime=None) -> _client() constructs McpStdioClient directly, which
    the autouse fake_mcp fixture has already replaced with
    FakeFoundryMcpClient module-wide."""
    context = ConnectorContext(
        project_id="p1",
        connection_id="c1",
        connection_name="Test",
        entity_service=cast(Any, None),
        edge_service=cast(Any, None),
        entity_store=cast(Any, None),
        edge_store=cast(Any, None),
        attachment_store=cast(Any, None),
        attachments_dir=cast(Any, None),
        link_store=cast(Any, None),
        runtime=None,
    )
    return FoundryConnector(
        FoundryConfig(mcp_server_path="C:/bridge/dist/index.js"), context
    )


@pytest.mark.asyncio
async def test_live_query_journals_uses_search_query_param_and_strips_html() -> None:
    """Against the real search-journals shape — a locator+snippet
    structure, not a flat list — verified live against a running Foundry
    world."""
    connector = _make_connector()

    chunks = await connector.query("Strahd", kind="journals")

    assert len(chunks) == 1
    assert chunks[0].title == "Session 3 notes — Lore"
    assert chunks[0].text == "The party met Strahd at the castle gate."
    call = next(
        c
        for i in FakeFoundryMcpClient.instances
        for c in i.calls
        if c[0] == "search-journals"
    )
    assert call[1] == {"searchQuery": "Strahd"}


@pytest.mark.asyncio
async def test_live_query_items_reaches_world_item_library_not_compendium() -> None:
    """Regression for the reported gap: "add all items from Foundry" only
    ever searched the compendium (the reference rulebook item database)
    because query_external_source had no "items" kind at all — the world's
    own standalone items (manage-world-items) were unreachable through
    chat no matter how the request was phrased."""
    connector = _make_connector()

    chunks = await connector.query("", kind="items")

    assert {c.title for c in chunks} == {"Кольцо сопротивления", "Молот"}
    hammer = next(c for c in chunks if c.title == "Молот")
    assert hammer.kind == "item"
    assert "weapon" in hammer.text
    assert "Оружие" in hammer.text
    call = next(
        c
        for i in FakeFoundryMcpClient.instances
        for c in i.calls
        if c[0] == "manage-world-items"
    )
    assert call[1] == {"action": "list"}


@pytest.mark.asyncio
async def test_live_query_items_passes_nonempty_query_as_name_filter() -> None:
    connector = _make_connector()

    await connector.query("Молот", kind="items")

    call = next(
        c
        for i in FakeFoundryMcpClient.instances
        for c in i.calls
        if c[0] == "manage-world-items"
    )
    assert call[1] == {"action": "list", "nameFilter": "Молот"}


@pytest.mark.asyncio
async def test_live_query_items_returns_more_than_the_old_five_item_cap() -> None:
    """Regression for the exact reported bug: "add all items from Foundry"
    only ever returned 5 of the world's real 11 items, with no indication
    anything was cut, because a single _LIVE_CHUNK_LIMIT=5 was shared
    across every result kind combined. Items now get their own budget
    (_ITEM_CHUNK_LIMIT=30), independent of journals/actors/compendium."""
    FakeFoundryMcpClient.world_item_count = 11
    connector = _make_connector()

    chunks = await connector.query("", kind="items")

    assert len(chunks) == 11


@pytest.mark.asyncio
async def test_live_query_default_kind_includes_world_items() -> None:
    """kind=None (the default when the assistant doesn't specify) fans out
    to journals/actors/items together — items must be included, not just
    reachable via an explicit kind="items" the model has to know to ask
    for."""
    connector = _make_connector()

    chunks = await connector.query("")

    assert any(c.kind == "item" for c in chunks)


# --- ingest (AI migration of a FOREIGN world) --------------------------------


@pytest.mark.asyncio
async def test_ingest_pulls_full_journal_pages_actors_and_items() -> None:
    """Migration reads journals in FULL (journalId+pageId), unlike
    import_data() which skips journals entirely and unlike query() which only
    gets a truncated search snippet. Actors and items are aggregated into one
    document each so short uniform records don't each cost an extraction
    call."""
    connector = _make_connector()

    documents = await connector.ingest_documents()

    by_kind = {doc.kind: doc for doc in documents}
    assert set(by_kind) == {"journal", "actor", "item"}

    journal = by_kind["journal"]
    assert journal.title == "SexSpace"
    assert journal.external_id == "journal-1"
    assert "## Описание" in journal.text
    # Full page content, HTML stripped — not a snippet, not markup soup.
    assert "Главный вход и гардероб" in journal.text
    assert "<p>" not in journal.text

    actors = by_kind["actor"]
    assert "Strahd" in actors.text and "Ireena" in actors.text
    assert "AC: 16" in actors.text

    assert "Кольцо сопротивления" in by_kind["item"].text


@pytest.mark.asyncio
async def test_ingest_skips_an_unreadable_page_without_sinking_the_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One bad page must not abort a whole world's migration."""
    connector = _make_connector()
    original = FakeFoundryMcpClient.call_tool

    async def flaky(
        self: FakeFoundryMcpClient, name: str, arguments: dict[str, Any]
    ) -> Any:
        if name == "list-journals" and "pageId" in arguments:
            raise ConnectorUnavailableError("Test", "page unreadable")
        return await original(self, name, arguments)

    monkeypatch.setattr(FakeFoundryMcpClient, "call_tool", flaky)

    documents = await connector.ingest_documents()

    # The journal is dropped (no readable pages), actors/items still arrive.
    assert {doc.kind for doc in documents} == {"actor", "item"}
