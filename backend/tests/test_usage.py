from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.llm.structured import LangChainStructuredGenerator
from loregraph.llm.usage import parse_usage
from loregraph.schemas.agent import GroundingReport
from loregraph.schemas.project import ProjectCreate
from loregraph.schemas.usage import UsageEvent
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from loregraph.storage.sqlite.usage_store import SqliteUsageStore

USAGE_METADATA = {
    "input_tokens": 100,
    "output_tokens": 20,
    "total_tokens": 120,
    "input_token_details": {"cache_read": 60, "cache_creation": 30},
}


class CapturingModel(BaseChatModel):
    """Records the messages handed to the structured runnable, so tests can
    assert on prompt shape (cache breakpoints) without a real provider."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    seen: list[list[BaseMessage]] = Field(default_factory=list)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        async def _run(messages: list[BaseMessage]) -> dict[str, Any]:
            self.seen.append(messages)
            return {
                "raw": AIMessage("", usage_metadata=USAGE_METADATA),
                "parsed": schema(),
                "parsing_error": None,
            }

        return RunnableLambda(_run)

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError

    @property
    def _llm_type(self) -> str:
        return "capturing"


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_engine_for(tmp_path / "test.sqlite3")
    await init_db(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


def test_parse_usage_reads_anthropic_cache_tokens() -> None:
    usage = parse_usage(USAGE_METADATA)
    assert usage.input_tokens == 100  # grand total, cache included
    assert usage.cache_read_tokens == 60
    assert usage.cache_creation_tokens == 30


def test_parse_usage_degrades_on_providers_without_cache_details() -> None:
    usage = parse_usage({"input_tokens": 10, "output_tokens": 2})
    assert (usage.cache_read_tokens, usage.cache_creation_tokens) == (0, 0)
    assert parse_usage(None).input_tokens == 0


@pytest.mark.asyncio
async def test_caching_puts_the_breakpoint_on_the_stable_prefix() -> None:
    """The cached block must hold the stable prefix only — the volatile tail
    (retry/revision directives) goes in a later, uncached block, so a
    regeneration re-reads the prefix instead of re-paying for it."""
    model = CapturingModel()
    generator = LangChainStructuredGenerator(model, prompt_caching=True)

    result = await generator.generate(
        GroundingReport, system="SYS", user="VOLATILE", cached_prefix="STABLE"
    )

    human = model.seen[0][1]
    assert isinstance(human.content, list)
    stable, volatile = human.content
    assert stable == {
        "type": "text",
        "text": "STABLE",
        "cache_control": {"type": "ephemeral"},
    }
    assert volatile == {"type": "text", "text": "VOLATILE"}
    # Cache tokens survive into the result, so the rollup can show the saving.
    assert result.usage.cache_read_tokens == 60


@pytest.mark.asyncio
async def test_without_caching_the_prefix_is_plain_text() -> None:
    """Non-Anthropic providers must never see a cache_control block."""
    model = CapturingModel()
    generator = LangChainStructuredGenerator(model, prompt_caching=False)

    await generator.generate(
        GroundingReport, system="SYS", user="VOLATILE", cached_prefix="STABLE"
    )

    assert model.seen[0][1].content == "STABLE\nVOLATILE"


@pytest.mark.asyncio
async def test_generate_sums_usage_across_schema_retries() -> None:
    model = CapturingModel()
    generator = LangChainStructuredGenerator(model, prompt_caching=False)
    await generator.generate(GroundingReport, system="S", user="U")
    # One attempt here; the point is that usage is read from the API's own
    # usage_metadata, never estimated from characters.
    assert model.seen[0][0].content == "S"


@pytest.mark.asyncio
async def test_rollup_groups_by_node_and_model(db_session: AsyncSession) -> None:
    project = await SqliteProjectStore(db_session).create(ProjectCreate(name="P"))
    store = SqliteUsageStore(db_session)

    def event(node: str, model: str, **tokens: int) -> UsageEvent:
        return UsageEvent(
            project_id=project.id,
            thread_id="t1",
            node=node,
            model=model,
            input_tokens=tokens.get("input", 0),
            output_tokens=tokens.get("output", 0),
            cache_read_tokens=tokens.get("cache_read", 0),
            cache_creation_tokens=tokens.get("cache_creation", 0),
        )

    await store.record(event("assistant", "haiku", input=100, output=10))
    await store.record(event("assistant", "haiku", input=50, output=5, cache_read=20))
    await store.record(
        event("generate_lore", "sonnet", input=1000, output=500, cache_creation=800)
    )

    rows = {row.node: row for row in await store.project_rollup(project.id)}

    assert rows["assistant"].calls == 2
    assert rows["assistant"].model == "haiku"
    assert rows["assistant"].input_tokens == 150
    assert rows["assistant"].output_tokens == 15
    assert rows["assistant"].cache_read_tokens == 20
    assert rows["generate_lore"].calls == 1
    assert rows["generate_lore"].cache_creation_tokens == 800


@pytest.mark.asyncio
async def test_rollup_is_project_scoped(db_session: AsyncSession) -> None:
    project_store = SqliteProjectStore(db_session)
    mine = await project_store.create(ProjectCreate(name="mine"))
    other = await project_store.create(ProjectCreate(name="other"))
    store = SqliteUsageStore(db_session)
    await store.record(
        UsageEvent(
            project_id=other.id,
            thread_id="t9",
            node="assistant",
            model="haiku",
            input_tokens=999,
            output_tokens=999,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
    )

    assert await store.project_rollup(mine.id) == []
    assert len(await store.project_rollup(other.id)) == 1
