"""On-demand tool-choice eval — NOT part of the regular pytest/CI run
(CLAUDE.md, "Тестирование промптов": eval sets with live model calls run by
request/nightly, never in CI).

Measures the thing golden_retrieval.py cannot: given a game master's question,
does the assistant reach for a tool that can actually answer it? Ranking
metrics score the order of a result list, but "сколько егоров в мире" has no
ranking answer at all, and a relationship question is unanswerable from entity
text however well it ranks. Every complaint that motivated this eval was a
tool-choice failure, not a ranking one.

Runs the real turn loop (assistant node + the real read tools over the
case's world), so what is scored is whether the assistant EVER consults a
tool that can answer — not just its opening move: looking a faction up by
name before asking about its relationships is correct, stopping there is not.

Costs real tokens: a few chat calls per case, on the configured provider (LLM
settings come from .env / the app's settings, same as production).

Usage (from backend/):
    uv run python -m evals.run_tool_choice_eval
    uv run python -m evals.run_tool_choice_eval --repeats 3
"""

import argparse
import asyncio
import statistics
import tempfile
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from evals.tool_choice_cases import CASES, PROJECT_ID, ToolChoiceCase
from loregraph.agent.nodes.assistant import assistant
from loregraph.agent.nodes.tools import run_tools
from loregraph.agent.skills.registry import pipeline_entry_node
from loregraph.agent.state import AgentState
from loregraph.config import Settings
from loregraph.exceptions import EntityNotFoundError
from loregraph.llm.embeddings import get_embedding_provider
from loregraph.llm.factory import ModelTier, get_chat_model
from loregraph.schemas.edge import EdgeOut
from loregraph.schemas.entity import EntityOut
from loregraph.schemas.project import ProjectOut
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore

# The tier the chat assistant runs on in production (api/deps.py builds the
# graph with tier="assistant") — measuring a different one would measure a
# model the game master never talks to.
ASSISTANT_TIER: ModelTier = "assistant"


class _EvalProjectStore:
    """The assistant node reads the project only for its agent_instructions;
    an eval world has none, and a real store would drag in a database."""

    async def get(self, project_id: str) -> ProjectOut:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        return ProjectOut(
            id=project_id,
            name="Eval world",
            description=None,
            agent_instructions=None,
            created_at=now,
            updated_at=now,
        )


class _EvalEntityStore:
    """The case's world, as the read protocol the tools use."""

    def __init__(self, entities: list[EntityOut]) -> None:
        self._by_id = {entity.id: entity for entity in entities}

    async def list_entities(
        self, project_id: str, entity_type: str | None = None
    ) -> list[EntityOut]:
        return [
            entity
            for entity in self._by_id.values()
            if entity.project_id == project_id
            and (entity_type is None or entity.type == entity_type)
        ]

    async def get(self, entity_id: str) -> EntityOut:
        try:
            return self._by_id[entity_id]
        except KeyError:
            raise EntityNotFoundError(entity_id) from None

    async def get_many(self, entity_ids: Sequence[str]) -> list[EntityOut]:
        return [self._by_id[eid] for eid in entity_ids if eid in self._by_id]


class _EvalEdgeStore:
    def __init__(self, edges: list[EdgeOut]) -> None:
        self._edges = edges

    async def list_all(
        self, project_id: str, edge_types: frozenset[str] | None = None
    ) -> list[EdgeOut]:
        return [
            edge
            for edge in self._edges
            if edge.project_id == project_id
            and (edge_types is None or edge.type in edge_types)
        ]

    async def list_for_entity(self, entity_id: str) -> list[EdgeOut]:
        return [
            edge
            for edge in self._edges
            if entity_id in (edge.source_entity_id, edge.target_entity_id)
        ]


# A full pass is dozens of chat calls in a row, which walks straight into a
# per-minute token limit on most accounts. Retrying is the eval's own problem
# to solve — a run that dies two thirds of the way through reports nothing.
_RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "429", "too many requests")
_BACKOFF_ATTEMPTS = 6


async def _with_backoff[T](call: Callable[[], Awaitable[T]]) -> T:
    """Retry a model call while the provider says "slow down".

    Matches on the message rather than a provider exception class on purpose:
    the LLM provider is swappable here (config.Settings.llm_provider), and
    importing openai's error type would tie the eval to one of them.
    """
    for attempt in range(_BACKOFF_ATTEMPTS):
        try:
            return await call()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            text = str(error).casefold()
            if not any(marker in text for marker in _RATE_LIMIT_MARKERS):
                raise
            if attempt == _BACKOFF_ATTEMPTS - 1:
                raise
            delay = 2.0 * 2**attempt
            print(f"  (rate limited, retrying in {delay:.0f}s)")
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


@asynccontextmanager
async def _case_knowledge_index(
    case: ToolChoiceCase, settings: Settings
) -> AsyncIterator[KnowledgeIndex | None]:
    """A real (temp-dir, real embedder) KnowledgeIndex for cases that upload
    reference documents — a fake embedder would test nothing about whether an
    IMPLICIT question ("Откуда Норвинтер получает энергию?", no mention of
    "document" or "upload") actually surfaces the relevant chunk; that is
    exactly the judgment call under measurement. None (same contour as
    production's "embeddings disabled") for every case with no kb_documents —
    the overwhelming majority — and also when this deployment's own settings
    have no embedder configured, which is reported rather than silently
    changing what the case measures."""
    if not case.kb_documents:
        yield None
        return
    embedder = get_embedding_provider(settings)
    if embedder is None:
        print(
            f"  ({case.case_id}: embeddings are disabled in this deployment's "
            "settings — search_knowledge_base will report unavailable)"
        )
        yield None
        return
    # ignore_cleanup_errors: ChromaVectorStore/chromadb.PersistentClient keeps
    # its sqlite file handle open for the process lifetime (no close()/dispose
    # exposed by either) — on Windows that makes the directory's own deletion
    # fail with WinError 32 ("file in use") on __exit__. Best-effort cleanup
    # (a leftover temp dir occasionally, on Windows only) beats a crashed eval
    # run; confirmed against a real PersistentClient in this session.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as kb_dir:
        knowledge_index = KnowledgeIndex(ChromaVectorStore(Path(kb_dir), embedder))
        await knowledge_index.index_source(PROJECT_ID, "eval-doc", case.kb_documents)
        yield knowledge_index


async def _tools_used(
    case: ToolChoiceCase, settings: Settings, max_turns: int
) -> tuple[list[str], frozenset[str]]:
    """Every tool the assistant calls across a whole turn loop, plus the set of
    existing-entity titles it named as propose_changes targets.

    Scoring only the FIRST call would be unfair and would measure the wrong
    thing: looking a faction up by name before asking about its relationships
    is a correct opening move, since get_entity_graph needs an id search_lore
    is what supplies. What failed for game masters was never the first call —
    it was stopping at search_lore and reporting "no such relationship".

    The target titles matter because create and edit are now one tool: the
    screenshot bug picked the right intent (change the world) but the wrong
    shape (clone Егор instead of editing him), which today shows up as a
    missing target id, not a wrong tool name.
    """
    entity_store = _EvalEntityStore(case.entities)
    edge_store = _EvalEdgeStore(case.edges)
    title_by_id = {entity.id: entity.title for entity in case.entities}
    chat_model = get_chat_model(settings, tier=ASSISTANT_TIER)
    state = AgentState(project_id=PROJECT_ID, messages=[HumanMessage(case.question)])
    used: list[str] = []
    target_titles: set[str] = set()

    async with _case_knowledge_index(case, settings) as knowledge_index:
        for _ in range(max_turns):
            update = await _with_backoff(
                partial(
                    assistant,
                    state,
                    chat_model=chat_model,
                    token_budget=100_000,
                    project_store=_EvalProjectStore(),  # type: ignore[arg-type]
                    usage_store=None,
                    model_name="eval",
                )
            )
            message = update["messages"][0]
            state = state.model_copy(
                update={"messages": [*state.messages, *update["messages"]]}
            )
            if not isinstance(message, AIMessage) or not message.tool_calls:
                break
            used.extend(call["name"] for call in message.tool_calls)
            for call in message.tool_calls:
                if call["name"] == "propose_changes":
                    for entity_id in call["args"].get("target_entity_ids", []) or []:
                        if entity_id in title_by_id:
                            target_titles.add(title_by_id[entity_id])
            # A branching skill (propose_changes / brainstorm_lore) ends the
            # chat turn in production — route_after_assistant hands off to its
            # pipeline instead of the read-tool executor. Mirroring that
            # (data-driven off the same registry) keeps the loop faithful and
            # stops here.
            if any(pipeline_entry_node(call["name"]) for call in message.tool_calls):
                break
            tool_update = await run_tools(
                state,
                vector_index=None,
                knowledge_index=knowledge_index,
                entity_store=entity_store,  # type: ignore[arg-type]
                edge_store=edge_store,  # type: ignore[arg-type]
            )
            state = state.model_copy(
                update={"messages": [*state.messages, *tool_update["messages"]]}
            )
    return used, frozenset(target_titles)


# A question here needs at most: find the entity, then open its graph.
MAX_TURNS = 4


async def run(repeats: int) -> list[tuple[str, float, Counter[str]]]:
    settings = Settings()
    rows: list[tuple[str, float, Counter[str]]] = []
    for case in CASES:
        picks: Counter[str] = Counter()
        hits = 0
        for _ in range(repeats):
            tools, targets = await _tools_used(case, settings, MAX_TURNS)
            picks.update(tools or ["(no tool call)"])
            # Correct when an acceptable tool was reached at some point in
            # the loop — extra calls alongside it are not a failure — AND, for
            # propose_changes cases, the right existing entities were named as
            # targets (create-vs-edit is now a target question, not a tool one).
            tool_ok = bool(case.acceptable_tools & set(tools))
            target_ok = (
                case.expected_target_titles is None
                or targets == case.expected_target_titles
            )
            if tool_ok and target_ok:
                hits += 1
        rows.append((case.case_id, hits / repeats, picks))
    return rows


def _print_report(rows: list[tuple[str, float, Counter[str]]]) -> None:
    width = max(len(case_id) for case_id, _, _ in rows)
    print(f"{'case':<{width}}  {'correct':>8}  tools called")
    for case_id, rate, picks in rows:
        # Plain ASCII: this prints to a Windows console whose default code
        # page (cp1251 on a Russian install) cannot encode "×", and a report
        # that crashes on its own separator is worse than an ugly one.
        called = ", ".join(f"{name} x{count}" for name, count in picks.most_common())
        print(f"{case_id:<{width}}  {rate:>8.2f}  {called}")
    print()
    print(f"mean tool-choice accuracy = {statistics.mean(r for _, r, _ in rows):.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Calls per case. Tool choice is sampled, so >1 shows how stable "
        "it is rather than one lucky draw.",
    )
    args = parser.parse_args()
    _print_report(asyncio.run(run(args.repeats)))


if __name__ == "__main__":
    main()
