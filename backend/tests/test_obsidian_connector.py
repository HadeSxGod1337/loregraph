"""Obsidian connector, end to end through the API (real SQLite, real vault
folder in tmp_path) — the same wiring the app uses, no mocks needed for a
file-based connector."""

from pathlib import Path

from fastapi.testclient import TestClient


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
    guild_note = (vault / "Loregraph" / "Faction" / "Smith Guild.md").read_text(
        "utf-8"
    )
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
