from fastapi import FastAPI
from fastapi.testclient import TestClient


def _doc(text: str) -> dict[str, object]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _make_player(client: TestClient, project_id: str, name: str = "Alice") -> str:
    """Create a player through the DM API and return the raw token."""
    created = client.post(
        f"/api/projects/{project_id}/players", json={"name": name}
    ).json()
    token = created["token"]
    assert isinstance(token, str) and token
    assert created["play_url"].endswith(f"/play/{token}")
    return token


def _player_client(app: FastAPI, token: str) -> TestClient:
    # A player reaches the app over the LAN — a non-loopback address — and
    # authenticates purely with the token.
    lan = TestClient(app, client=("192.168.1.77", 5))
    resp = lan.post("/api/play/session", json={"token": token})
    assert resp.status_code == 200
    return lan


def _reveal(
    client: TestClient,
    project_id: str,
    entity_id: str,
    *,
    player_text: dict[str, object] | None = None,
    visible: list[str] | None = None,
) -> None:
    client.put(
        f"/api/projects/{project_id}/entities/{entity_id}/player-view",
        json={
            "revealed_to_players": True,
            "player_text": player_text,
            "visible_field_keys": visible or [],
        },
    )


def test_player_sees_only_revealed_entities_and_fields(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    mira = client.post(
        f"/api/projects/{project_id}/entities",
        json={
            "type": "npc",
            "title": "Mira",
            "fields": [
                {"key": "faction", "field_type": "text", "value": "Guild"},
                {"key": "secret", "field_type": "text", "value": "double agent"},
            ],
        },
    ).json()
    client.post(
        f"/api/projects/{project_id}/entities",
        json={"type": "npc", "title": "Hidden"},
    )
    _reveal(
        client,
        project_id,
        mira["id"],
        player_text=_doc("A friendly smith."),
        visible=["faction"],
    )

    token = _make_player(client, project_id)
    player = _player_client(app, token)

    entities = player.get("/api/play/entities").json()
    assert [e["title"] for e in entities] == ["Mira"]
    entity = entities[0]
    assert {f["key"] for f in entity["fields"]} == {"faction"}
    assert entity["player_text"]["content"][0]["content"][0]["text"] == (
        "A friendly smith."
    )
    # DM-only metadata never crosses the wire.
    assert "created_at" not in entity
    assert "template_id" not in entity

    # A hidden entity is 404 by id, never confirming it exists.
    hidden_ids = [
        e["id"]
        for e in client.get(f"/api/projects/{project_id}/entities").json()
        if e["title"] == "Hidden"
    ]
    assert player.get(f"/api/play/entities/{hidden_ids[0]}").status_code == 404


def test_player_graph_excludes_edges_to_hidden(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    a = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "A"}
    ).json()
    b = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "B"}
    ).json()
    c = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "C"}
    ).json()
    for edge in (
        {"source_entity_id": a["id"], "target_entity_id": b["id"], "type": "ally"},
        {"source_entity_id": a["id"], "target_entity_id": c["id"], "type": "foe"},
    ):
        client.post(f"/api/projects/{project_id}/edges", json=edge)
    _reveal(client, project_id, a["id"])
    _reveal(client, project_id, b["id"])

    player = _player_client(app, _make_player(client, project_id))
    graph = player.get("/api/play/graph").json()
    assert {n["title"] for n in graph["nodes"]} == {"A", "B"}
    assert len(graph["edges"]) == 1


def test_revoked_and_rotated_tokens(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    created = client.post(
        f"/api/projects/{project_id}/players", json={"name": "Bob"}
    ).json()
    token = created["token"]
    player_id = created["id"]

    # Works before revoke.
    assert _player_client(app, token)

    client.post(f"/api/projects/{project_id}/players/{player_id}/revoke")
    lan = TestClient(app, client=("192.168.1.77", 5))
    assert lan.post("/api/play/session", json={"token": token}).status_code == 401

    # Rotating issues a new working token and reactivates the player; the old
    # one stays dead.
    rotated = client.post(
        f"/api/projects/{project_id}/players/{player_id}/rotate"
    ).json()
    assert lan.post("/api/play/session", json={"token": token}).status_code == 401
    assert (
        lan.post("/api/play/session", json={"token": rotated["token"]}).status_code
        == 200
    )


def test_token_cannot_reach_another_project(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    other = client.post("/api/projects", json={"name": "Other"}).json()
    secret = client.post(
        f"/api/projects/{other['id']}/entities",
        json={"type": "npc", "title": "Secret"},
    ).json()
    _reveal(client, other["id"], secret["id"])  # revealed, but in the OTHER project

    player = _player_client(app, _make_player(client, project_id))
    # The token's project comes from the token, not the URL, so the other
    # project's revealed entity is invisible.
    assert player.get("/api/play/entities").json() == []
    assert player.get(f"/api/play/entities/{secret['id']}").status_code == 404


def test_player_can_fetch_revealed_attachment_only(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    revealed = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "Shown"}
    ).json()
    hidden = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "Nope"}
    ).json()
    shown_url = client.post(
        f"/api/entities/{revealed['id']}/attachments",
        files={"file": ("a.txt", b"ok", "text/plain")},
    ).json()["url"]
    hidden_url = client.post(
        f"/api/entities/{hidden['id']}/attachments",
        files={"file": ("b.txt", b"no", "text/plain")},
    ).json()["url"]
    _reveal(client, project_id, revealed["id"])

    player = _player_client(app, _make_player(client, project_id))
    assert player.get(shown_url).status_code == 200
    assert player.get(hidden_url).status_code == 404
    # Traversal is still blocked for a player token.
    assert (
        player.get(f"/files/{revealed['id']}/..%2f..%2fcampaign.sqlite3").status_code
        == 404
    )
