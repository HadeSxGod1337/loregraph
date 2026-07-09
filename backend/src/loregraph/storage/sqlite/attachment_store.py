import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import AttachmentNotFoundError
from loregraph.schemas.attachment import AttachmentOut
from loregraph.storage.sqlite.models import AttachmentRow


class SqliteAttachmentStore:
    def __init__(self, session: AsyncSession, attachments_dir: Path) -> None:
        self._session = session
        self._attachments_dir = attachments_dir

    async def create(
        self,
        entity_id: str,
        original_filename: str,
        content_type: str,
        content: bytes,
    ) -> AttachmentOut:
        suffix = Path(original_filename).suffix
        stored_filename = f"{uuid.uuid4().hex}{suffix}"
        dest_path = self._attachments_dir / entity_id / stored_filename
        await asyncio.to_thread(_write_file, dest_path, content)

        row = AttachmentRow(
            id=uuid.uuid4().hex,
            entity_id=entity_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            content_type=content_type,
            size_bytes=len(content),
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def list_for_entity(self, entity_id: str) -> list[AttachmentOut]:
        stmt = select(AttachmentRow).where(AttachmentRow.entity_id == entity_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def delete(self, attachment_id: str) -> None:
        row = await self._session.get(AttachmentRow, attachment_id)
        if row is None:
            raise AttachmentNotFoundError(attachment_id)
        path = self._attachments_dir / row.entity_id / row.stored_filename
        await self._session.delete(row)
        await self._session.commit()
        await asyncio.to_thread(path.unlink, missing_ok=True)


def _write_file(dest_path: Path, content: bytes) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(content)


def attachment_url(row: AttachmentRow) -> str:
    return f"/files/{row.entity_id}/{row.stored_filename}"


def _row_to_out(row: AttachmentRow) -> AttachmentOut:
    return AttachmentOut(
        id=row.id,
        entity_id=row.entity_id,
        url=attachment_url(row),
        original_filename=row.original_filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )
