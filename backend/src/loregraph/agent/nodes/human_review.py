from typing import Any

from langgraph.types import interrupt

from loregraph.agent.state import AgentState
from loregraph.schemas.agent import AgentResumeRequest, AgentReviewPayload


def build_review_payload(state: AgentState) -> AgentReviewPayload:
    return AgentReviewPayload(
        draft=state.draft,
        warnings=state.warnings,
        input_tokens=state.input_tokens,
        output_tokens=state.output_tokens,
    )


async def human_review(state: AgentState) -> dict[str, Any]:
    """The mandatory HITL gate: the graph pauses here (checkpointed to disk)
    until the DM resumes with an explicit decision. Nothing reaches canon
    without passing through this node."""
    if state.draft is None:
        # Nothing to review (e.g. budget ran out before the first
        # generation) — don't trap the session at an empty interrupt;
        # commit's no-draft branch reports the warnings to the chat.
        return {"decision_action": None}
    raw_decision = interrupt(build_review_payload(state).model_dump(mode="json"))
    decision = AgentResumeRequest.model_validate(raw_decision)
    update: dict[str, Any] = {"decision_action": decision.action}
    if decision.draft is not None:
        # DM edits win: entities removed, titles changed, relationships
        # dropped — whatever survives review is what gets committed (or, on
        # revise, becomes the base the model must preserve).
        update["draft"] = decision.draft
    if decision.action == "revise":
        update["revision_feedback"] = decision.feedback or "improve the draft"
        update["attempts"] = 0  # a fresh revision gets its own dedup retries
        update["warnings"] = []
    return update


def route_after_review(state: AgentState) -> str:
    return "revise" if state.decision_action == "revise" else "commit"
