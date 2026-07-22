from typing import Any

from langgraph.types import interrupt

from loregraph.agent.state import AgentState
from loregraph.schemas.agent import AgentResumeRequest, AgentReviewPayload


def build_review_payload(state: AgentState) -> AgentReviewPayload:
    return AgentReviewPayload(
        draft=state.draft,
        entity_edit_draft=state.entity_edit_draft,
        warnings=state.warnings,
        input_tokens=state.input_tokens,
        output_tokens=state.output_tokens,
    )


async def human_review(state: AgentState) -> dict[str, Any]:
    """The mandatory HITL gate: the graph pauses here (checkpointed to disk)
    until the DM resumes with an explicit decision. Nothing reaches canon
    without passing through this node."""
    has_content = state.draft is not None or state.entity_edit_draft is not None
    if not has_content:
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
    """Approve/reject always fall through to commit; a revise has to go back
    to the node that produced what is on screen.

    Every "propose" skill shares this one review gate, so the return value has
    to name its pipeline — sending a revised entity edit or relationship set
    to generate_lore would run the creative lore generator over a draft it
    never made."""
    if state.decision_action != "revise":
        return "commit"
    if state.entity_edit_draft is not None:
        return "revise_edit"
    if state.pending_entity_ids:
        return "revise_relationships"
    return "revise_lore"
