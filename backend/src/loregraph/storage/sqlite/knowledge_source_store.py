import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import KnowledgeSourceNotFoundError
from loregraph.schemas.knowledge import KnowledgeSourceOut
from loregraph.storage.sqlite.models import KnowledgeSourceRow


class SqliteKnowledgeSourceStore:
    def __init__(self, session: AsyncSession, knowledge_dir: Path) -> None:
        self._session = session
        self._knowledge_dir = knowledge_dir

    async def create(
        self,
        project_id: str,
        original_filename: str,
        content_type: str,
        content: bytes,
    ) -> KnowledgeSourceOut:
        suffix = Path(original_filename).suffix
        stored_filename = f"{uuid.uuid4().hex}{suffix}"
        dest_path = self._knowledge_dir / project_id / stored_filename
        await asyncio.to_thread(_write_file, dest_path, content)

        now = datetime.now(UTC)
        row = KnowledgeSourceRow(
            id=uuid.uuid4().hex,
            project_id=project_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            content_type=content_type,
            size_bytes=len(content),
            status="pending",
            error=None,
            chunk_count=0,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def list_for_project(self, project_id: str) -> list[KnowledgeSourceOut]:
        stmt = select(KnowledgeSourceRow).where(
            KnowledgeSourceRow.project_id == project_id
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def get(self, source_id: str) -> KnowledgeSourceOut:
        row = await self._session.get(KnowledgeSourceRow, source_id)
        if row is None:
            raise KnowledgeSourceNotFoundError(source_id)
        return _row_to_out(row)

    async def update_status(
        self,
        source_id: str,
        *,
        status: str,
        error: str | None = None,
        chunk_count: int | None = None,
    ) -> KnowledgeSourceOut:
        row = await self._session.get(KnowledgeSourceRow, source_id)
        if row is None:
            raise KnowledgeSourceNotFoundError(source_id)
        row.status = status
        row.error = error
        if chunk_count is not None:
            row.chunk_count = chunk_count
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def delete(self, source_id: str) -> None:
        row = await self._session.get(KnowledgeSourceRow, source_id)
        if row is None:
            raise KnowledgeSourceNotFoundError(source_id)
        path = self._knowledge_dir / row.project_id / row.stored_filename
        await self._session.delete(row)
        await self._session.commit()
        await asyncio.to_thread(path.unlink, missing_ok=True)


def _write_file(dest_path: Path, content: bytes) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(content)


def _row_to_out(row: KnowledgeSourceRow) -> KnowledgeSourceOut:
    return KnowledgeSourceOut(
        id=row.id,
        project_id=row.project_id,
        original_filename=row.original_filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        status=row.status,
        error=row.error,
        chunk_count=row.chunk_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
