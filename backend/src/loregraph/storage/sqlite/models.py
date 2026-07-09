from datetime import datetime

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EntityRow(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(primary_key=True)
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
    source_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    target_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(index=True)
    label: Mapped[str | None]
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
