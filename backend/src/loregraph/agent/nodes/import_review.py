from typing import Any

from langgraph.types import interrupt

from loregraph.agent.import_state import ImportState
from loregraph.schemas.agent import LoreDraft
from loregraph.schemas.import_job import ImportReviewDecision, ImportReviewPayload

NODE = "import_paginate_review"

# UI-manageable page size — large enough that a 1000+-chunk document
# doesn't need dozens of pages, small enough that one page is still
# reviewable at a glance. Purely presentational: no LLM calls happen
# between pages, so paging is fast regardless of size.
REVIEW_SLICE_SIZE = 15


def paginate_review(state: ImportState) -> dict[str, Any]:
    """Splits the deduplicated entity set into reviewer-sized pages — pure
    presentation, no LLM calls, so moving between pages during review never
    waits on generation (unlike the chat pipeline's per-batch propose_lore,
    where every review comes from a fresh LLM call)."""
    entities = state.merged_entities
    slices = [
        LoreDraft(entities=entities[i : i + REVIEW_SLICE_SIZE], relationships=[])
        for i in range(0, len(entities), REVIEW_SLICE_SIZE)
    ] or [LoreDraft(entities=[], relationships=[])]
    return {"review_slices": slices, "current_slice": 0}


def build_review_payload(state: ImportState) -> ImportReviewPayload:
    return ImportReviewPayload(
        slice_index=state.current_slice,
        total_slices=len(state.review_slices),
        draft=state.review_slices[state.current_slice],
        merge_notes=state.merge_notes,
        warnings=state.warnings,
        input_tokens=state.input_tokens,
        output_tokens=state.output_tokens,
    )


async def review_slice(state: ImportState) -> dict[str, Any]:
    """The bulk-import job's only HITL gate — deliberately the only node
    that calls interrupt(). Every window's extraction and the whole merge
    pass have already run by the time this fires (see agent/import_graph.py
    for why interrupt() must never sit inside the parallel per-window
    calls), so approving is instant — no waiting on generation between
    pages, unlike the chat pipeline where a "revise" regenerates via a
    fresh LLM call."""
    raw_decision = interrupt(build_review_payload(state).model_dump(mode="json"))
    decision = ImportReviewDecision.model_validate(raw_decision)
    update: dict[str, Any] = {"decision_action": decision.action}
    if decision.draft is not None:
        slices = list(state.review_slices)
        slices[state.current_slice] = decision.draft
        update["review_slices"] = slices
    return update


def route_after_slice_review(state: ImportState) -> str:
    return "commit" if state.decision_action in ("approve", "approve_all") else "skip"
