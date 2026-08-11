from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_player_access import _make_player, _player_client, _reveal


def _doc(text: str) -> dict[str, object]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _revealed_npc(client: TestClient, project_id: str) -> str:
    entity = client.post(
        f"/api/projects/{project_id}/entities", json={"type": "npc", "title": "Mira"}
    ).json()
    _reveal(client, project_id, entity["id"])
    entity_id = entity["id"]
    assert isinstance(entity_id, str)
    return entity_id


def test_note_visibility_between_players(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    entity_id = _revealed_npc(client, project_id)
    alice = _player_client(app, _make_player(client, project_id, "Alice"))
    bob = _player_client(app, _make_player(client, project_id, "Bob"))

    alice.post(
        f"/api/play/entities/{entity_id}/notes",
        json={"body": _doc("alice-private"), "is_public": False},
    )
    alice.post(
        f"/api/play/entities/{entity_id}/notes",
        json={"body": _doc("alice-public"), "is_public": True},
    )

    # Bob sees only Alice's public note, marked not-own.
    bob_view = bob.get(f"/api/play/entities/{entity_id}/notes").json()
    assert len(bob_view) == 1
    assert bob_view[0]["is_own"] is False
    assert bob_view[0]["author_name"] == "Alice"

    # Alice sees both of hers.
    alice_view = alice.get(f"/api/play/entities/{entity_id}/notes").json()
    assert len(alice_view) == 2
    assert all(n["is_own"] for n in alice_view)


def test_player_cannot_edit_or_delete_others_note(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    entity_id = _revealed_npc(client, project_id)
    alice = _player_client(app, _make_player(client, project_id, "Alice"))
    bob = _player_client(app, _make_player(client, project_id, "Bob"))

    note = alice.post(
        f"/api/play/entities/{entity_id}/notes",
        json={"body": _doc("mine"), "is_public": True},
    ).json()

    assert bob.put(
        f"/api/play/notes/{note['id']}",
        json={"body": _doc("hax"), "is_public": True},
    ).status_code == 404
    assert bob.delete(f"/api/play/notes/{note['id']}").status_code == 404

    # Alice can edit and delete her own.
    assert alice.put(
        f"/api/play/notes/{note['id']}",
        json={"body": _doc("edited"), "is_public": False},
    ).status_code == 200
    assert alice.delete(f"/api/play/notes/{note['id']}").status_code == 204


def test_dm_sees_all_notes_including_private(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    entity_id = _revealed_npc(client, project_id)
    alice = _player_client(app, _make_player(client, project_id, "Alice"))
    alice.post(
        f"/api/play/entities/{entity_id}/notes",
        json={"body": _doc("private thoughts"), "is_public": False},
    )

    dm_view = client.get(
        f"/api/projects/{project_id}/entities/{entity_id}/player-notes"
    ).json()
    assert len(dm_view) == 1
    assert dm_view[0]["author_name"] == "Alice"
    # The DM is not a player, so nothing reads as "own".
    assert dm_view[0]["is_own"] is False


def test_deleting_player_removes_their_notes(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    entity_id = _revealed_npc(client, project_id)
    created = client.post(
        f"/api/projects/{project_id}/players", json={"name": "Alice"}
    ).json()
    alice = _player_client(app, created["token"])
    alice.post(
        f"/api/play/entities/{entity_id}/notes",
        json={"body": _doc("mine"), "is_public": True},
    )

    client.delete(f"/api/projects/{project_id}/players/{created['id']}")
    dm_view = client.get(
        f"/api/projects/{project_id}/entities/{entity_id}/player-notes"
    ).json()
    assert dm_view == []
