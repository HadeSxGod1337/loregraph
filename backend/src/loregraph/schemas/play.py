from typing import Any

from pydantic import BaseModel

from loregraph.schemas.edge import EdgeOut
from loregraph.schemas.entity import AttachmentRef, EntityFieldOut


class PlaySessionOut(BaseModel):
    """What a player's client learns about its own session after exchanging a
    token — never the token, and nothing about other players."""

    player_id: str
    project_id: str
    project_name: str
    name: str


class PlayerEntityOut(BaseModel):
    """An entity as one player may see it. Assembled on the server so the
    client never receives what it isn't allowed to. Deliberately omits DM-only
    metadata: created_at/updated_at, template_id, project_id."""

    id: str
    type: str
    title: str
    icon: AttachmentRef | None = None
    player_text: dict[str, Any] | None = None
    # Only fields the DM whitelisted (visible_to_players); everything else is
    # dropped before it leaves the server.
    fields: list[EntityFieldOut] = []
    pos_x: float | None = None
    pos_y: float | None = None


class PlayerSubgraphOut(BaseModel):
    nodes: list[PlayerEntityOut]
    edges: list[EdgeOut]


class PlaySessionRequest(BaseModel):
    token: str
