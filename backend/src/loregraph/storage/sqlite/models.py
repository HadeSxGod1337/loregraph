from datetime import datetime

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str | None] = mapped_column(default=None)
    # DM's free-text style/format preferences, blended into agent system prompts
    # (see prompts.project_instructions_block) — added post-launch, so init_db's
    # migration step must backfill this column on existing databases.
    agent_instructions: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class EntityRow(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(index=True)
    title: Mapped[str]
    fields: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    # Not an FK: built-in template ids are code strings, not rows.
    template_id: Mapped[str | None] = mapped_column(default=None)
    icon_attachment_id: Mapped[str | None] = mapped_column(
        ForeignKey("attachments.id", ondelete="SET NULL"), default=None
    )
    icon: Mapped["AttachmentRow | None"] = relationship(
        foreign_keys=[icon_attachment_id], lazy="joined", viewonly=True
    )
    # NULL = auto-layout should place this node; set = the user dragged it.
    # Global per-entity (not per root/depth view) so a position survives
    # root/depth changes in the graph view.
    pos_x: Mapped[float | None] = mapped_column(default=None)
    pos_y: Mapped[float | None] = mapped_column(default=None)
    # Limited player access. Both nullable because init_db can only ADD COLUMN
    # (no backfill, see db.py): NULL == not revealed / no player text. The API
    # contract is a strict bool, coerced on read.
    revealed_to_players: Mapped[bool | None] = mapped_column(default=None)
    player_text: Mapped[dict[str, object] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class EdgeRow(Base):
    __tablename__ = "edges"

    id: Mapped[str] = mapped_column(primary_key=True)
    # Denormalized from source/target's own project_id (both are validated to
    # match at creation — see routers/edges.py) so project-scoped queries
    # don't need a join against entities.
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    target_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(index=True)
    label: Mapped[str | None]
    created_at: Mapped[datetime]


class EntityTemplateRow(Base):
    """A user-defined entity template (field skeleton + sheet layout) scoped to
    one project. Built-in templates are NOT stored here — they live in code
    (see templates/builtins.py) and are merged in at the service layer. Layout
    and field defs are JSON blobs for the same reason EntityRow.fields is: the
    template shape is data, not a rigid table schema."""

    __tablename__ = "entity_templates"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str]
    entity_type: Mapped[str] = mapped_column(index=True)
    icon: Mapped[str | None] = mapped_column(default=None)
    field_defs: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    layout: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    external_embed: Mapped[dict[str, object] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class SheetPresetRow(Base):
    """A user-saved sheet preset (field defs + one Section) scoped to one
    project. Built-in presets are NOT stored here — they live in code (see
    templates/presets.py) and are merged in at the service layer, same split
    as EntityTemplateRow/builtins.py."""

    __tablename__ = "sheet_presets"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str]
    field_defs: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    section: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class AgentSessionRow(Base):
    """Catalog of agent runs. The LangGraph checkpointer owns the graph
    *state*; this table owns the *listing* (review queue, statuses, usage) so
    the UI never has to enumerate checkpoint threads."""

    __tablename__ = "agent_sessions"

    thread_id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(index=True)
    instruction: Mapped[str]
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    # JSON list of entity ids created by an approved run (a run commits a
    # whole lore batch, not a single entity).
    committed_entities_json: Mapped[str | None] = mapped_column(default=None)
    # Snapshot of the review payload at interrupt time — lets list/detail
    # endpoints work without compiling a graph or touching the checkpointer.
    review_json: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ImportJobRow(Base):
    """Catalog of bulk-import jobs (see agent/import_graph.py). Same split
    as AgentSessionRow: the ImportState checkpointer owns the graph state,
    this table owns the listing/progress so the UI never has to enumerate
    checkpoint threads."""

    __tablename__ = "import_jobs"

    job_id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str]
    source_filename: Mapped[str]
    status: Mapped[str] = mapped_column(index=True)
    total_windows: Mapped[int] = mapped_column(default=0)
    total_slices: Mapped[int] = mapped_column(default=0)
    current_slice: Mapped[int] = mapped_column(default=0)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    committed_entities_json: Mapped[str | None] = mapped_column(default=None)
    # Snapshot of the review payload at interrupt time — same rationale as
    # AgentSessionRow.review_json.
    review_json: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class UsageEventRow(Base):
    """One recorded LLM call. The per-session totals on AgentSessionRow are a
    denormalized fast path for the review UI; this table is the granular
    source of truth (per node, per model, incl. cache tokens) that the
    /projects/{id}/usage rollup aggregates."""

    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Not an FK to agent_sessions: usage is worth keeping even if a session row
    # is later pruned, and the project-scoped CASCADE above already bounds it.
    thread_id: Mapped[str] = mapped_column(index=True)
    node: Mapped[str] = mapped_column(index=True)
    model: Mapped[str] = mapped_column(index=True)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cache_read_tokens: Mapped[int] = mapped_column(default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime]


class AttachmentRow(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(primary_key=True)
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str]
    stored_filename: Mapped[str] = mapped_column(unique=True)
    content_type: Mapped[str]
    size_bytes: Mapped[int]
    created_at: Mapped[datetime]


class ConnectionRow(Base):
    """A configured link to an external DM tool (Obsidian vault, Foundry MCP
    bridge, LongStoryShort…). Config is stored as plaintext JSON on purpose:
    localhost single-user app whose DB already holds the whole campaign, and
    .env already holds LLM keys the same way — the API layer masks secret
    fields on the way out instead (see api/routers/connections.py)."""

    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    connector_type: Mapped[str] = mapped_column(index=True)
    name: Mapped[str]
    config_json: Mapped[str] = mapped_column(default="{}")
    # Include this connection's live data as grounding context in the agent's
    # lore-generation pipeline (retrieve_context), not just as a chat tool.
    use_for_grounding: Mapped[bool] = mapped_column(default=False)
    # Export freshly committed entities right after an approved agent run.
    auto_push_after_commit: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ConnectionEntityLinkRow(Base):
    """Provenance mapping between a Loregraph entity and the external
    document/record it corresponds to in one connection (vault file path,
    Foundry actor id, LSS character id). Lets exports update-not-duplicate
    and imports dedupe-not-clone."""

    __tablename__ = "connection_entity_links"

    id: Mapped[str] = mapped_column(primary_key=True)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(index=True)
    # What kind of external object external_id names: "md_file", "actor",
    # "journal", "lss_character", …
    external_kind: Mapped[str]
    last_synced_at: Mapped[datetime]


class PlayerRow(Base):
    """A player invited to view a project. The token is stored as a hash only:
    the row travels in project exports and backups, and a plaintext token there
    would be a standing key to the world. A lost link is not recovered, it is
    rotated (see api/routers/players.py)."""

    __tablename__ = "players"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str]
    token_hash: Mapped[str] = mapped_column(unique=True, index=True)  # sha256 hex
    # First few chars of the raw token, so the DM can tell links apart in the
    # UI without the secret ever being stored in full.
    token_prefix: Mapped[str]
    # NULL = active. Set = revoked; the note history is kept (revoke != delete).
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    last_seen_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class PlayerNoteRow(Base):
    """A note a player keeps on one entity. Public notes are visible to the
    whole party (and the DM); private ones only to their author and the DM.
    Cascades from both the player (a note without its author is orphaned
    scribble) and the entity."""

    __tablename__ = "player_notes"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[str] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    is_public: Mapped[bool] = mapped_column(default=False)
    body: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)  # ProseMirror
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class AppSettingRow(Base):
    """One UI-set override of a `Settings` field (see services/settings_service.py).

    Key/value rather than a column per setting: the set of configurable fields
    changes with every new provider, and a schema migration per checkbox is a
    cost with no benefit here — the whitelist in config.py, not the table
    shape, is what bounds which fields may be written.

    Values are stored as JSON so a bool stays a bool and an int stays an int.
    API keys live here in plaintext for the same reason ConnectionRow's config
    does: a localhost single-user app whose database already holds the entire
    campaign. The API masks them on the way out and never logs them.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value_json: Mapped[str]
    updated_at: Mapped[datetime]


class KnowledgeSourceRow(Base):
    """A reference document (rulebook, setting bible) uploaded to a project's
    knowledge base — grounding material for the agent, kept out of the
    world-canon entity graph on purpose (see services/knowledge_index.py)."""

    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str]
    stored_filename: Mapped[str] = mapped_column(unique=True)
    content_type: Mapped[str]
    size_bytes: Mapped[int]
    # pending -> processing -> ready|failed (see services/knowledge_ingest.py)
    status: Mapped[str] = mapped_column(index=True)
    error: Mapped[str | None] = mapped_column(default=None)
    chunk_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
