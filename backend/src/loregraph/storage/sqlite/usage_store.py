import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.schemas.usage import UsageEvent, UsageRollupRow
from loregraph.storage.sqlite.models import UsageEventRow


class SqliteUsageStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, event: UsageEvent) -> None:
        self._session.add(
            UsageEventRow(
                id=uuid.uuid4().hex,
                project_id=event.project_id,
                thread_id=event.thread_id,
                node=event.node,
                model=event.model,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                cache_read_tokens=event.cache_read_tokens,
                cache_creation_tokens=event.cache_creation_tokens,
                created_at=datetime.now(UTC),
            )
        )
        await self._session.commit()

    async def project_rollup(self, project_id: str) -> list[UsageRollupRow]:
        stmt = (
            select(
                UsageEventRow.node,
                UsageEventRow.model,
                func.count().label("calls"),
                func.coalesce(func.sum(UsageEventRow.input_tokens), 0),
                func.coalesce(func.sum(UsageEventRow.output_tokens), 0),
                func.coalesce(func.sum(UsageEventRow.cache_read_tokens), 0),
                func.coalesce(func.sum(UsageEventRow.cache_creation_tokens), 0),
            )
            .where(UsageEventRow.project_id == project_id)
            .group_by(UsageEventRow.node, UsageEventRow.model)
            .order_by(UsageEventRow.node, UsageEventRow.model)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            UsageRollupRow(
                node=node,
                model=model,
                calls=calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens,
            )
            for (
                node,
                model,
                calls,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_creation_tokens,
            ) in rows
        ]
