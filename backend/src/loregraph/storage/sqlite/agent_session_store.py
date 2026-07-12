import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.exceptions import AgentSessionNotFoundError
from loregraph.schemas.agent import (
    AgentReviewPayload,
    AgentSessionOut,
    AgentSessionStatus,
)
from loregraph.storage.sqlite.models import AgentSessionRow


class SqliteAgentSessionStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, project_id: str, thread_id: str) -> AgentSessionOut:
        now = datetime.now(UTC)
        row = AgentSessionRow(
            thread_id=thread_id,
            project_id=project_id,
            status="idle",
            # The DB column keeps its historical name; it holds the
            # conversation title (first user message, truncated).
            instruction="",
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _row_to_out(row)

    async def get(self, thread_id: str) -> AgentSessionOut:
        row = await self._get_row(thread_id)
        return _row_to_out(row)

    async def list_for_project(self, project_id: str) -> list[AgentSessionOut]:
        stmt = (
            select(AgentSessionRow)
            .where(AgentSessionRow.project_id == project_id)
            .order_by(AgentSessionRow.created_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_out(row) for row in rows]

    async def update(
        self,
        thread_id: str,
        *,
        status: AgentSessionStatus | None = None,
        title: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        committed_entity_ids: list[str] | None = None,
        review: AgentReviewPayload | None = None,
        clear_review: bool = False,
    ) -> AgentSessionOut:
        row = await self._get_row(thread_id)
        if status is not None:
            row.status = status
        if title is not None:
            row.instruction = title
        if clear_review:
            row.review_json = None
        if input_tokens is not None:
            row.input_tokens = input_tokens
        if output_tokens is not None:
            row.output_tokens = output_tokens
        if committed_entity_ids is not None:
            row.committed_entities_json = json.dumps(committed_entity_ids)
        if review is not None:
            row.review_json = review.model_dump_json()
        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _row_to_out(row)

    async def _get_row(self, thread_id: str) -> AgentSessionRow:
        row = await self._session.get(AgentSessionRow, thread_id)
        if row is None:
            raise AgentSessionNotFoundError(thread_id)
        return row


def _row_to_out(row: AgentSessionRow) -> AgentSessionOut:
    review = (
        AgentReviewPayload.model_validate_json(row.review_json)
        if row.review_json
        else None
    )
    committed: list[str] = (
        json.loads(row.committed_entities_json) if row.committed_entities_json else []
    )
    return AgentSessionOut(
        thread_id=row.thread_id,
        project_id=row.project_id,
        status=row.status,  # type: ignore[arg-type]  # constrained at write time
        title=row.instruction,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        committed_entity_ids=committed,
        review=review,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
