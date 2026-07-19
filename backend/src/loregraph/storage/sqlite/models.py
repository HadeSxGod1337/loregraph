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
