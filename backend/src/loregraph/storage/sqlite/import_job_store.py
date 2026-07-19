import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import ImportJobNotFoundError
from loregraph.schemas.import_job import (
    ImportJobOut,
    ImportJobStatus,
    ImportReviewPayload,
)
from loregraph.storage.sqlite.models import ImportJobRow


class SqliteImportJobStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, project_id: str, job_id: str, source_id: str, source_filename: str
    ) -> ImportJobOut:
        now = datetime.now(UTC)
        row = ImportJobRow(
            job_id=job_id,
            project_id=project_id,
            source_id=source_id,
            source_filename=source_filename,
            status="planning",
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def get(self, job_id: str) -> ImportJobOut:
        row = await self._get_row(job_id)
        return _row_to_out(row)

    async def list_for_project(self, project_id: str) -> list[ImportJobOut]:
        stmt = (
            select(ImportJobRow)
            .where(ImportJobRow.project_id == project_id)
            .order_by(ImportJobRow.created_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def update(
        self,
        job_id: str,
        *,
        status: ImportJobStatus | None = None,
        total_windows: int | None = None,
        total_slices: int | None = None,
        current_slice: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        committed_entity_ids: list[str] | None = None,
        review: ImportReviewPayload | None = None,
        clear_review: bool = False,
    ) -> ImportJobOut:
        row = await self._get_row(job_id)
        if status is not None:
            row.status = status
        if total_windows is not None:
            row.total_windows = total_windows
        if total_slices is not None:
            row.total_slices = total_slices
        if current_slice is not None:
            row.current_slice = current_slice
        if input_tokens is not None:
            row.input_tokens = input_tokens
        if output_tokens is not None:
            row.output_tokens = output_tokens
        if committed_entity_ids is not None:
            row.committed_entities_json = json.dumps(committed_entity_ids)
        if clear_review:
            row.review_json = None
        if review is not None:
            row.review_json = review.model_dump_json()
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def _get_row(self, job_id: str) -> ImportJobRow:
        row = await self._session.get(ImportJobRow, job_id)
        if row is None:
            raise ImportJobNotFoundError(job_id)
        return row


def _row_to_out(row: ImportJobRow) -> ImportJobOut:
    review = (
        ImportReviewPayload.model_validate_json(row.review_json)
        if row.review_json
        else None
    )
    committed: list[str] = (
        json.loads(row.committed_entities_json) if row.committed_entities_json else []
    )
    return ImportJobOut(
        job_id=row.job_id,
        project_id=row.project_id,
        source_id=row.source_id,
        source_filename=row.source_filename,
        status=row.status,  # type: ignore[arg-type]  # constrained at write time
        total_windows=row.total_windows,
        total_slices=row.total_slices,
        current_slice=row.current_slice,
        committed_entity_ids=committed,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        review=review,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
