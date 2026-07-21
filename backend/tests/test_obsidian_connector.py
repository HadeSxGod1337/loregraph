"""Obsidian connector, end to end through the API (real SQLite, real vault
folder in tmp_path) — the same wiring the app uses, no mocks needed for a
file-based connector."""

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.obsidian.connector import ObsidianConfig, ObsidianConnector


def _make_connection(client: TestClient, project_id: str, vault: Path) -> str:
    resp = client.post(
        f"/api/projects/{project_id}/connections",
        json={
            "connector_type": "obsidian",
            "name": "My Vault",
            "config": {"vault_path": str(vault)},
        },
    )
    assert resp.status_code == 201, resp.text
    connection_id = resp.json()["id"]
    assert isinstance(connection_id, str)
    return connection_id


def _create_entity(
    client: TestClient, project_id: str, entity_type: str, title: str, **kwargs: object
) -> str:
    resp = client.post(
        f"/api/projects/{project_id}/entities",
        json={"type": entity_type, "title": title, **kwargs},
    )
    assert resp.status_code == 201, resp.text
    entity_id = resp.json()["id"]
    assert isinstance(entity_id, str)
    return entity_id


def test_probe_reports_missing_vault(client: TestClient, project_id: str) -> None:
    resp = client.post(
        f"/api/projects/{project_id}/connections",
        json={
            "connector_type": "obsidian",
            "name": "Ghost Vault",
            "config": {"vault_path": "Z:/definitely/not/here"},
        },
    )
    connection_id = resp.json()["id"]
    probe = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/test"
    ).json()
    assert probe["ok"] is False
    assert probe["detail_code"] == "vault_path_missing"


def test_export_writes_markdown_with_wikilinks(
    client: TestClient, project_id: str, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    npc_id = _create_entity(
        client,
        project_id,
        "npc",
        "Mira Kuznetz",
        fields=[
            {"key": "role", "field_type": "text", "value": "blacksmith"},
            {"key": "level", "field_type": "number", "value": 5},
            {"key": "tags", "field_type": "tag", "value": ["guild", "ally"]},
        ],
    )
    faction_id = _create_entity(client, project_id, "faction", "Smith Guild")
    edge = client.post(
        f"/api/projects/{project_id}/edges",
        json={
            "source_entity_id": npc_id,
            "target_entity_id": faction_id,
            "type": "member_of",
            "label": "founding member",
        },
    )
    assert edge.status_code == 201, edge.text
    connection_id = _make_connection(client, project_id, vault)

    preview = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/export/preview",
        json={},
    ).json()
    assert {item["action"] for item in preview["items"]} == {"create"}
    assert len(preview["items"]) == 2

    result = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/export",
        json={},
    ).json()
    assert result == {"created": 2, "updated": 0, "skipped": 0, "errors": []}

    note = (vault / "Loregraph" / "Npc" / "Mira Kuznetz.md").read_text("utf-8")
    # Snapshot of the note shape (CLAUDE.md: snapshot-test .md with wikilinks).
    assert note == (
        "---\n"
        f"loregraph_id: {npc_id}\n"
        "type: npc\n"
        "role: blacksmith\n"
        "level: 5\n"
        "tags:\n"
        "- guild\n"
        "- ally\n"
        "---\n"
        "\n"
        "# Mira Kuznetz\n"
        "\n"
        "## Relationships\n"
        "\n"
        "- member_of → [[Smith Guild]] — founding member\n"
    )
    guild_note = (vault / "Loregraph" / "Faction" / "Smith Guild.md").read_text("utf-8")
    assert "- member_of ← [[Mira Kuznetz]] — founding member" in guild_note

    # Second export is an update, not a duplicate.
    second = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/export",
        json={},
    ).json()
    assert second["updated"] == 2 and second["created"] == 0


def test_rename_moves_note_file(
    client: TestClient, project_id: str, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    entity_id = _create_entity(client, project_id, "npc", "Old Name")
    connection_id = _make_connection(client, project_id, vault)
    url = f"/api/projects/{project_id}/connections/{connection_id}/export"
    client.post(url, json={})
    assert (vault / "Loregraph" / "Npc" / "Old Name.md").is_file()

    client.put(
        f"/api/projects/{project_id}/entities/{entity_id}",
        json={"type": "npc", "title": "New Name", "fields": []},
    )
    client.post(url, json={})
    assert not (vault / "Loregraph" / "Npc" / "Old Name.md").exists()
    assert (vault / "Loregraph" / "Npc" / "New Name.md").is_file()


def test_import_roundtrip_updates_by_loregraph_id(
    client: TestClient, project_id: str, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    entity_id = _create_entity(
        client,
        project_id,
        "npc",
        "Torvald",
        fields=[{"key": "role", "field_type": "text", "value": "guard"}],
    )
    connection_id = _make_connection(client, project_id, vault)
    base = f"/api/projects/{project_id}/connections/{connection_id}"
    client.post(f"{base}/export", json={})

    # DM edits the note in Obsidian: changes a frontmatter field.
    note_path = vault / "Loregraph" / "Npc" / "Torvald.md"
    note_path.write_text(
        note_path.read_text("utf-8").replace("role: guard", "role: captain"),
        encoding="utf-8",
    )
    result = client.post(f"{base}/import", json={"payload": {}}).json()
    assert result["updated"] == 1 and result["created"] == 0

    entity = client.get(f"/api/projects/{project_id}/entities/{entity_id}").json()
    role = next(f for f in entity["fields"] if f["key"] == "role")
    assert role["value"] == "captain"


def test_import_creates_new_entities_and_edges_from_new_note(
    client: TestClient, project_id: str, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    folder = vault / "Loregraph" / "Npc"
    folder.mkdir(parents=True)
    _create_entity(client, project_id, "faction", "Iron Ring")
    connection_id = _make_connection(client, project_id, vault)
    (folder / "Vex.md").write_text(
        "---\ntype: npc\n---\n\n# Vex\n\nA fence for stolen goods, works "
        "with [[Iron Ring]].\n\n## Relationships\n\n"
        "- member_of → [[Iron Ring]] — informal\n",
        encoding="utf-8",
    )
    result = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {}},
    ).json()
    assert result["created"] == 1
    assert result["errors"] == []

    entities = client.get(f"/api/projects/{project_id}/entities").json()
    vex = next(e for e in entities if e["title"] == "Vex")
    assert vex["type"] == "npc"
    edges = client.get(
        f"/api/projects/{project_id}/edges", params={"entity_id": vex["id"]}
    ).json()
    assert len(edges) == 1
    assert edges[0]["type"] == "member_of"

    # Re-import: same edge is deduped, entity updated in place (LWW).
    again = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {}},
    ).json()
    assert again["created"] == 0 and again["updated"] == 1
    assert again["skipped"] == 1  # the already-existing edge


def test_import_malformed_note_reports_error_without_aborting(
    client: TestClient, project_id: str, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    folder = vault / "Loregraph"
    folder.mkdir(parents=True)
    (folder / "bad.md").write_text(
        "---\n: not: [valid yaml\n---\n\n# Bad\n", encoding="utf-8"
    )
    (folder / "good.md").write_text("# Good\n\nFine note.\n", encoding="utf-8")
    connection_id = _make_connection(client, project_id, vault)
    result = client.post(
        f"/api/projects/{project_id}/connections/{connection_id}/import",
        json={"payload": {}},
    ).json()
    assert result["created"] == 1  # good.md landed
    assert len(result["errors"]) == 1
    assert result["errors"][0]["ref"] == "bad.md"


# --- ingest (AI migration of a FOREIGN vault) --------------------------------


def _ingest_connector(vault: Path) -> ObsidianConnector:
    """Connector built directly against a vault, for testing ingest_documents
    (the IngestSource method the migration pipeline calls) without the
    HTTP/DB stack — it touches no stores."""
    context = ConnectorContext(
        project_id="p1",
        connection_id="c1",
        connection_name="My Vault",
        entity_service=cast(Any, None),
        edge_service=cast(Any, None),
        entity_store=cast(Any, None),
        edge_store=cast(Any, None),
        attachment_store=cast(Any, None),
        attachments_dir=cast(Any, None),
        link_store=cast(Any, None),
        runtime=None,
    )
    return ObsidianConnector(ObsidianConfig(vault_path=str(vault)), context)


@pytest.mark.asyncio
async def test_ingest_reads_the_whole_vault_not_just_our_subfolder(
    tmp_path: Path,
) -> None:
    """The migration case: a vault Loregraph never exported to. Notes outside
    our own subfolder — the entire point — must be picked up verbatim, with
    no Loregraph frontmatter or relationship syntax required."""
    vault = tmp_path / "vault"
    (vault / "Characters").mkdir(parents=True)
    (vault / "Loregraph").mkdir(parents=True)
    (vault / "Characters" / "Strahd.md").write_text(
        "# Strahd\n\nLord of Barovia, sworn enemy of Ireena.\n", encoding="utf-8"
    )
    (vault / "Loregraph" / "Ours.md").write_text(
        "---\nloregraph_id: abc\n---\n\n# Ours\n", encoding="utf-8"
    )

    documents = await _ingest_connector(vault).ingest_documents()

    by_title = {doc.title: doc for doc in documents}
    assert set(by_title) == {"Strahd", "Ours"}
    strahd = by_title["Strahd"]
    assert strahd.kind == "note"
    assert strahd.external_id == "Characters/Strahd.md"
    assert "sworn enemy of Ireena" in strahd.text


@pytest.mark.asyncio
async def test_ingest_skips_attachments_and_empty_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "_attachments").mkdir(parents=True)
    (vault / "_attachments" / "note.md").write_text("# Attached\n", encoding="utf-8")
    (vault / "blank.md").write_text("   \n", encoding="utf-8")
    (vault / "real.md").write_text("# Real\n\nContent.\n", encoding="utf-8")

    documents = await _ingest_connector(vault).ingest_documents()

    assert [doc.title for doc in documents] == ["real"]
