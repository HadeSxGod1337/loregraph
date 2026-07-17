"""Regression suite over evals/hallucination_cases.py: the deterministic
tier of verify_grounding (relationship-endpoint and citation checks) must
keep catching every planted hallucination and never flag a clean draft.
Unlike evals/run_hallucination_eval.py's printed report, this is a CI-safe
assertion suite — no LLM calls, no network, deterministic like the rest of
the guard it tests."""

from typing import cast

import pytest

from evals.hallucination_cases import CASES, HallucinationCase
from evals.metrics import hallucination_catch_rate
from loregraph.agent.nodes.verify_grounding import verify_grounding
from loregraph.agent.state import AgentState
from loregraph.llm.structured import StructuredGenerator
from loregraph.schemas.agent import AgentWarning

_GUARD_CODES = frozenset(
    {"dropped_unknown_source", "dropped_unknown_target", "uncited_lore_id"}
)


async def _guard_warnings(case: HallucinationCase) -> list[AgentWarning]:
    state = AgentState(
        project_id="eval",
        pending_brief="eval",
        context_entity_ids=case.context_entity_ids,
        draft=case.draft,
    )
    update = await verify_grounding(
        state,
        extraction=cast(StructuredGenerator, None),  # unused: token_budget=0 below
        token_budget=0,
        usage_store=None,
        model_name="eval",
    )
    return cast(list[AgentWarning], update.get("warnings", []))


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
async def test_guard_catches_every_planted_hallucination(
    case: HallucinationCase,
) -> None:
    warnings = await _guard_warnings(case)
    flagged = sum(1 for w in warnings if w.code in _GUARD_CODES)
    assert hallucination_catch_rate(flagged, case.poisoned_claim_count) == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [c for c in CASES if c.poisoned_claim_count == 0],
    ids=[c.case_id for c in CASES if c.poisoned_claim_count == 0],
)
async def test_guard_has_no_false_positives_on_clean_drafts(
    case: HallucinationCase,
) -> None:
    warnings = await _guard_warnings(case)
    flagged = [w for w in warnings if w.code in _GUARD_CODES]
    assert flagged == []
