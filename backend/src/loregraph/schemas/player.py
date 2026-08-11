from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PlayerCreate(BaseModel):
    name: str


class PlayerOut(BaseModel):
    """A player as the DM sees them — never the token, only its short prefix.
    `play_url` and `note_count` are filled in by the router (they depend on
    the configured host and a notes count join, not on the player row)."""

    id: str
    project_id: str
    name: str
    token_prefix: str
    revoked: bool = False
    last_seen_at: datetime | None = None
    note_count: int = 0
    play_url: str | None = None
    created_at: datetime
    updated_at: datetime


class PlayerCreatedOut(PlayerOut):
    """Returned once, right after create or rotate. The raw token is shown a
    single time and never persisted in the clear — a lost link is rotated,
    not recovered."""

    token: str


# --- notes -------------------------------------------------------------------


class PlayerNoteWrite(BaseModel):
    body: dict[str, Any]  # ProseMirror doc
    is_public: bool = False


class PlayerNoteRecord(BaseModel):
    """Storage-level view of a note: carries `author_player_id` so a service
    can decide whether the current viewer owns it. Not returned to clients —
    the API shape is PlayerNoteOut, which replaces the id with `is_own`."""

    id: str
    project_id: str
    author_player_id: str
    author_name: str
    entity_id: str
    is_public: bool
    body: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PlayerNoteOut(BaseModel):
    """A note as one viewer sees it. `is_own` is computed per request from the
    viewer's identity; the author's player id is deliberately omitted."""

    id: str
    entity_id: str
    author_name: str
    is_own: bool
    is_public: bool
    body: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(
        cls, record: PlayerNoteRecord, *, viewer_player_id: str | None
    ) -> "PlayerNoteOut":
        return cls(
            id=record.id,
            entity_id=record.entity_id,
            author_name=record.author_name,
            is_own=record.author_player_id == viewer_player_id,
            is_public=record.is_public,
            body=record.body,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
