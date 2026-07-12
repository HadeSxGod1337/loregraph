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
