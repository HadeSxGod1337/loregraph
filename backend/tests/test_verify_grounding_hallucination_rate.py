"""Covers the numeric hallucination_rate verify_grounding.py derives from
GroundingReport.claims_checked/claims_flagged, alongside the pre-existing
free-text warnings — see agent/nodes/verify_grounding.py."""

import pytest
from pydantic import BaseModel

from loregraph.agent.nodes.verify_grounding import verify_grounding
from loregraph.agent.state import NO_LORE_SENTINEL, AgentState
from loregraph.llm.structured import StructuredResult
from loregraph.llm.usage import LLMCallUsage
from loregraph.schemas.agent import DraftEntity, GroundingReport, LoreDraft

pytestmark = pytest.mark.asyncio


class FakeExtraction:
    def __init__(self, report: GroundingReport) -> None:
        self._report = report

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        assert schema is GroundingReport
        value = self._report
        assert isinstance(value, schema)
        return StructuredResult(value, LLMCallUsage(input_tokens=10, output_tokens=5))


def _draft() -> LoreDraft:
    return LoreDraft(
        entities=[DraftEntity(ref="e1", type="npc", title="Voss", summary="...")]
    )


def _state(
    existing_lore: str = '<entity id="npc_mira">Mira Smith</entity>',
) -> AgentState:
    return AgentState(
        project_id="p1",
        existing_lore=existing_lore,
        context_entity_ids=["npc_mira"],
        draft=_draft(),
    )


async def test_hallucination_rate_is_computed_from_claim_counts() -> None:
    report = GroundingReport(claims_checked=4, claims_flagged=1, warnings=["bad claim"])
    update = await verify_grounding(
        _state(),
        extraction=FakeExtraction(report),
        token_budget=1000,
        usage_store=None,
        model_name="test",
    )
    assert update["grounding_hallucination_rate"] == 0.25
    assert any(w.code == "llm_text" for w in update["warnings"])


async def test_zero_claims_checked_reports_no_rate() -> None:
    report = GroundingReport(claims_checked=0, claims_flagged=0, warnings=[])
    update = await verify_grounding(
        _state(),
        extraction=FakeExtraction(report),
        token_budget=1000,
        usage_store=None,
        model_name="test",
    )
    assert "grounding_hallucination_rate" not in update


async def test_claims_flagged_is_clamped_to_claims_checked() -> None:
    # Nothing in the schema stops the model from returning an inconsistent
    # count — the rate must never exceed 1.0 regardless.
    report = GroundingReport(claims_checked=2, claims_flagged=5, warnings=["x", "y"])
    update = await verify_grounding(
        _state(),
        extraction=FakeExtraction(report),
        token_budget=1000,
        usage_store=None,
        model_name="test",
    )
    assert update["grounding_hallucination_rate"] == 1.0


async def test_llm_judge_tier_skipped_without_lore_reports_no_rate() -> None:
    report = GroundingReport(claims_checked=3, claims_flagged=1, warnings=["x"])
    update = await verify_grounding(
        _state(existing_lore=NO_LORE_SENTINEL),
        extraction=FakeExtraction(report),
        token_budget=1000,
        usage_store=None,
        model_name="test",
    )
    assert "grounding_hallucination_rate" not in update


async def test_llm_judge_tier_skipped_over_budget_reports_no_rate() -> None:
    report = GroundingReport(claims_checked=3, claims_flagged=1, warnings=["x"])
    update = await verify_grounding(
        _state(),
        extraction=FakeExtraction(report),
        token_budget=0,
        usage_store=None,
        model_name="test",
    )
    assert "grounding_hallucination_rate" not in update
