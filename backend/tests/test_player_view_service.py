import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loregraph.exceptions import EntityNotFoundError, PlayerNoteNotFoundError
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import (
    EntityCreate,
    EntityFieldIn,
    EntityPlayerViewUpdate,
    FieldType,
)
from loregraph.services.player_view import PlayerViewService
from loregraph.storage.sqlite.db import create_engine_for, init_db, make_session_factory
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.models import ProjectRow
from loregraph.storage.sqlite.player_note_store import SqlitePlayerNoteStore
from loregraph.storage.sqlite.player_store import SqlitePlayerStore

pytestmark = pytest.mark.asyncio


async def _factory(tmp_path: Path) -> async_sessionmaker[AsyncSession]:
    engine = create_engine_for(tmp_path / "t.sqlite3")
    await init_db(engine)
    return make_session_factory(engine)


async def _project(factory: async_sessionmaker[AsyncSession]) -> str:
    pid = uuid.uuid4().hex
    async with factory() as session:
        now = datetime.now(UTC)
        session.add(ProjectRow(id=pid, name="P", created_at=now, updated_at=now))
        await session.commit()
    return pid


def _doc(text: str) -> dict[str, object]:
    return {"type": "doc", "content": [{"type": "text", "text": text}]}


async def test_only_revealed_entities_and_whitelisted_fields(tmp_path: Path) -> None:
    factory = await _factory(tmp_path)
    pid = await _project(factory)
    async with factory() as session:
        entities = SqliteEntityStore(session)
        mira = await entities.create(
            EntityCreate(
                type="npc",
                title="Mira",
                fields=[
                    EntityFieldIn(
                        key="faction", field_type=FieldType.TEXT, value="Guild"
                    ),
                    EntityFieldIn(
                        key="secret", field_type=FieldType.TEXT, value="agent"
                    ),
                ],
            ),
            pid,
        )
        await entities.create(EntityCreate(type="npc", title="Hidden"), pid)
        await entities.set_player_view(
            mira.id,
            EntityPlayerViewUpdate(
                revealed_to_players=True,
                player_text=_doc("A smith."),
                visible_field_keys=["faction"],
            ),
        )
        service = PlayerViewService(
            entities, SqliteEdgeStore(session), SqlitePlayerNoteStore(session)
        )

        revealed = await service.list_revealed(pid)
        assert [e.title for e in revealed] == ["Mira"]
        assert {f.key for f in revealed[0].fields} == {"faction"}
        assert revealed[0].player_text == _doc("A smith.")

        with pytest.raises(EntityNotFoundError):
            await service.get_revealed(pid, "does-not-exist")


async def test_subgraph_drops_edges_into_hidden_entities(tmp_path: Path) -> None:
    factory = await _factory(tmp_path)
    pid = await _project(factory)
    async with factory() as session:
        entities = SqliteEntityStore(session)
        edges = SqliteEdgeStore(session)
        a = await entities.create(EntityCreate(type="npc", title="A"), pid)
        b = await entities.create(EntityCreate(type="npc", title="B"), pid)
        c = await entities.create(EntityCreate(type="npc", title="C"), pid)
        for e in (a, b):
            await entities.set_player_view(
                e.id,
                EntityPlayerViewUpdate(revealed_to_players=True),
            )
        await edges.create(
            EdgeCreate(source_entity_id=a.id, target_entity_id=b.id, type="ally"), pid
        )
        # Edge into the hidden C must never appear.
        await edges.create(
            EdgeCreate(source_entity_id=a.id, target_entity_id=c.id, type="foe"), pid
        )
        service = PlayerViewService(entities, edges, SqlitePlayerNoteStore(session))

        graph = await service.revealed_subgraph(pid)
        assert {n.title for n in graph.nodes} == {"A", "B"}
        assert len(graph.edges) == 1
        assert graph.edges[0].type == "ally"


async def test_note_visibility_and_ownership(tmp_path: Path) -> None:
    factory = await _factory(tmp_path)
    pid = await _project(factory)
    async with factory() as session:
        entities = SqliteEntityStore(session)
        players = SqlitePlayerStore(session)
        notes = SqlitePlayerNoteStore(session)
        npc = await entities.create(EntityCreate(type="npc", title="Mira"), pid)
        await entities.set_player_view(
            npc.id, EntityPlayerViewUpdate(revealed_to_players=True)
        )
        alice = await players.create(pid, "Alice", "ha", "pa")
        bob = await players.create(pid, "Bob", "hb", "pb")
        service = PlayerViewService(entities, SqliteEdgeStore(session), notes)

        await service.create_note(pid, npc.id, alice.id, _doc("mine-private"), False)
        await service.create_note(pid, npc.id, alice.id, _doc("mine-public"), True)
        bob_note = await service.create_note(
            pid, npc.id, bob.id, _doc("bob-private"), False
        )

        # Alice sees her own two, not Bob's private one.
        alice_view = await service.list_visible_notes(pid, npc.id, alice.id)
        assert {n.is_own for n in alice_view} == {True}
        assert len(alice_view) == 2

        # Bob sees his own private plus Alice's public, with correct is_own.
        bob_view = await service.list_visible_notes(pid, npc.id, bob.id)
        texts = {n.body["content"][0]["text"]: n.is_own for n in bob_view}
        assert texts == {"bob-private": True, "mine-public": False}

        # Alice cannot edit or delete Bob's note.
        with pytest.raises(PlayerNoteNotFoundError):
            await service.update_own_note(bob_note.id, alice.id, _doc("hax"), True)
        with pytest.raises(PlayerNoteNotFoundError):
            await service.delete_own_note(bob_note.id, alice.id)


async def test_notes_on_hidden_entity_are_not_reachable(tmp_path: Path) -> None:
    factory = await _factory(tmp_path)
    pid = await _project(factory)
    async with factory() as session:
        entities = SqliteEntityStore(session)
        players = SqlitePlayerStore(session)
        hidden = await entities.create(EntityCreate(type="npc", title="Hidden"), pid)
        alice = await players.create(pid, "Alice", "ha", "pa")
        service = PlayerViewService(
            entities, SqliteEdgeStore(session), SqlitePlayerNoteStore(session)
        )
        with pytest.raises(EntityNotFoundError):
            await service.list_visible_notes(pid, hidden.id, alice.id)
        with pytest.raises(EntityNotFoundError):
            await service.create_note(pid, hidden.id, alice.id, _doc("x"), True)
