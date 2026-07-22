"""On-demand grounding-guard eval — NOT part of the regular pytest/CI run.

Exercises the real deterministic tier of agent/nodes/verify_grounding.py
against the golden hallucination_cases.py (no mocks). The LLM-as-judge tier
is skipped on purpose (token_budget=0 forces state.over_budget() True) since
it needs a live model call — that belongs to CLAUDE.md's nightly/on-request
eval tier, not this harness. Reports the deterministic guard's catch rate
and any false positives on clean drafts, i.e. the fraction of hallucinated
claims that would slip past this line of defense.

Usage (from backend/):
    uv run python -m evals.run_hallucination_eval
"""

import asyncio
from typing import cast

from evals.hallucination_cases import CASES, HallucinationCase
from evals.metrics import hallucination_catch_rate
from loregraph.agent.nodes.verify_grounding import verify_grounding
from loregraph.agent.state import AgentState
from loregraph.llm.structured import StructuredGenerator
from loregraph.schemas.agent import AgentWarning
from loregraph.schemas.edge import EdgeOut
from loregraph.storage.protocols import EdgeStore

_GUARD_CODES = frozenset(
    {"dropped_unknown_source", "dropped_unknown_target", "uncited_lore_id"}
)


class _NoEdges:
    """The cases here plant hallucinated endpoints and citations, not
    contradictions with an existing graph — so this harness runs against a
    world with no relationships and only the guard under test speaks up."""

    async def list_all(
        self, project_id: str, edge_types: frozenset[str] | None = None
    ) -> list[EdgeOut]:
        return []


async def _run_case(case: HallucinationCase) -> list[AgentWarning]:
    state = AgentState(
        project_id="eval",
        pending_brief="eval",
        context_entity_ids=case.context_entity_ids,
        draft=case.draft,
    )
    update = await verify_grounding(
        state,
        # Unused: token_budget=0 skips the LLM-as-judge branch entirely, so
        # the extraction client is never called.
        extraction=cast(StructuredGenerator, None),
        token_budget=0,
        edge_store=cast(EdgeStore, _NoEdges()),
        usage_store=None,
        model_name="eval",
    )
    return cast(list[AgentWarning], update.get("warnings", []))


async def run() -> None:
    total_planted = 0
    total_caught = 0
    false_positives = 0
    rows: list[tuple[str, int, int]] = []

    for case in CASES:
        warnings = await _run_case(case)
        flagged = sum(1 for w in warnings if w.code in _GUARD_CODES)
        caught = min(flagged, case.poisoned_claim_count)
        total_planted += case.poisoned_claim_count
        total_caught += caught
        if case.poisoned_claim_count == 0:
            false_positives += flagged
        rows.append((case.case_id, case.poisoned_claim_count, flagged))

    width = max(len(case_id) for case_id, _, _ in rows)
    print(f"{'case':<{width}}  planted  flagged")
    for case_id, planted, flagged in rows:
        print(f"{case_id:<{width}}  {planted:>7}  {flagged:>7}")

    catch_rate = hallucination_catch_rate(total_caught, total_planted)
    print(
        f"\nguard catch rate           = {total_caught}/{total_planted}"
        f" = {catch_rate:.2%}"
    )
    print(f"hallucination pass-through  = {1 - catch_rate:.2%}")
    print(f"false positives on clean drafts = {false_positives}")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
