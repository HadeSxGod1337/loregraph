"""The single place an entity becomes what a player is allowed to see.

Routers do no filtering — they call this service — so a new player endpoint
can't forget the reveal check or leak a hidden field. All filtering is on the
server; the client never receives what it may not see.
"""

from loregraph.exceptions import EntityNotFoundError, PlayerNoteNotFoundError
from loregraph.schemas.entity import EntityOut
from loregraph.schemas.play import PlayerEntityOut, PlayerSubgraphOut
from loregraph.schemas.player import PlayerNoteOut
from loregraph.services.graph_query import edges_among
from loregraph.storage.protocols import EdgeStore, EntityStore, PlayerNoteStore


class PlayerViewService:
    def __init__(
        self,
        entity_store: EntityStore,
        edge_store: EdgeStore,
        note_store: PlayerNoteStore,
    ) -> None:
        self._entity_store = entity_store
        self._edge_store = edge_store
        self._note_store = note_store

    async def list_revealed(self, project_id: str) -> list[PlayerEntityOut]:
        entities = await self._entity_store.list_entities(project_id)
        return [_to_player_entity(e) for e in entities if e.revealed_to_players]

    async def get_revealed(self, project_id: str, entity_id: str) -> PlayerEntityOut:
        entity = await self._entity_store.get(entity_id)
        # Wrong project or not revealed -> 404, not 403: never confirm a hidden
        # entity exists (same rule as EntityService.get_in_project).
        if entity.project_id != project_id or not entity.revealed_to_players:
            raise EntityNotFoundError(entity_id)
        return _to_player_entity(entity)

    async def revealed_subgraph(self, project_id: str) -> PlayerSubgraphOut:
        entities = await self._entity_store.list_entities(project_id)
        revealed = [e for e in entities if e.revealed_to_players]
        revealed_ids = {e.id for e in revealed}
        # edges_among keeps only edges with BOTH ends revealed, so an edge into
        # a hidden entity never even reaches the response.
        edges = await edges_among(self._edge_store, project_id, revealed_ids)
        return PlayerSubgraphOut(
            nodes=[_to_player_entity(e) for e in revealed], edges=edges
        )

    async def list_visible_notes(
        self, project_id: str, entity_id: str, viewer_player_id: str
    ) -> list[PlayerNoteOut]:
        # Reveal check first: a player can't read notes on an entity they can't
        # see (raises 404 if hidden/other project).
        await self.get_revealed(project_id, entity_id)
        records = await self._note_store.list_for_entity(entity_id)
        return [
            PlayerNoteOut.from_record(r, viewer_player_id=viewer_player_id)
            for r in records
            if r.is_public or r.author_player_id == viewer_player_id
        ]

    async def create_note(
        self,
        project_id: str,
        entity_id: str,
        player_id: str,
        body: dict[str, object],
        is_public: bool,
    ) -> PlayerNoteOut:
        await self.get_revealed(project_id, entity_id)
        record = await self._note_store.create(
            project_id, player_id, entity_id, body, is_public
        )
        return PlayerNoteOut.from_record(record, viewer_player_id=player_id)

    async def update_own_note(
        self,
        note_id: str,
        player_id: str,
        body: dict[str, object],
        is_public: bool,
    ) -> PlayerNoteOut:
        await self._require_own(note_id, player_id)
        record = await self._note_store.update(note_id, body, is_public)
        return PlayerNoteOut.from_record(record, viewer_player_id=player_id)

    async def delete_own_note(self, note_id: str, player_id: str) -> None:
        await self._require_own(note_id, player_id)
        await self._note_store.delete(note_id)

    async def _require_own(self, note_id: str, player_id: str) -> None:
        record = await self._note_store.get(note_id)
        # Someone else's note is treated as nonexistent — 404, never 403.
        if record.author_player_id != player_id:
            raise PlayerNoteNotFoundError(note_id)


def _to_player_entity(entity: EntityOut) -> PlayerEntityOut:
    return PlayerEntityOut(
        id=entity.id,
        type=entity.type,
        title=entity.title,
        icon=entity.icon,
        player_text=entity.player_text,
        fields=[f for f in entity.fields if f.visible_to_players],
        pos_x=entity.pos_x,
        pos_y=entity.pos_y,
    )
