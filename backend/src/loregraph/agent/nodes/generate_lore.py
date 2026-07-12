from typing import Any

from loregraph.agent.state import AgentState
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import project_instructions_block, render
from loregraph.schemas.agent import LoreDraft
from loregraph.storage.protocols import ProjectStore

BUDGET_EXHAUSTED_WARNING = (
    "Token budget for this run is exhausted — generation stopped early."
)


def _revision_block(state: AgentState) -> str:
    """When the DM asked for changes at review, revise the current draft
    instead of regenerating from scratch — cheaper and keeps what they liked."""
    if not state.revision_feedback or state.draft is None:
        return ""
    return (
        "\nYou are REVISING your previous draft. Keep everything the game "
        "master did not criticize (same refs, same titles), change only what "
        "the feedback asks for.\n"
        f"<previous_draft>\n{state.draft.model_dump_json()}\n</previous_draft>\n"
        f"<feedback>\n{state.revision_feedback}\n</feedback>"
    )


async def generate_lore(
    state: AgentState,
    *,
    creative: StructuredGenerator,
    token_budget: int,
    project_store: ProjectStore,
) -> dict[str, Any]:
    """One creative call produces a coherent batch: entities (types chosen by
    the model, steered toward the project's existing taxonomy) plus the
    relationship web between them and to existing lore."""
    if state.over_budget(token_budget):
        # Never silently burn the user's key past the ceiling: surface the
        # stop at review instead (docs/agent_architecture.md, section 9).
        # retry_feedback is cleared AND attempts advanced: check_duplicates_
        # draft re-arms retry_feedback for the unchanged draft, so without
        # the attempts bump the generate↔check cycle would loop forever.
        return {
            "warnings": [*state.warnings, BUDGET_EXHAUSTED_WARNING],
            "retry_feedback": "",
            "attempts": state.attempts + 1,
        }

    retry_feedback = (
        f"\nIMPORTANT — previous attempt was rejected: {state.retry_feedback}"
        if state.retry_feedback
        else ""
    )
    project = await project_store.get(state.project_id)
    result = await creative.generate(
        LoreDraft,
        system=render(
            "generate_lore.system.md",
            project_instructions_block=project_instructions_block(
                project.agent_instructions
            ),
        ),
        user=render(
            "generate_lore.user.md",
            existing_lore=state.existing_lore,
            knowledge_context=state.knowledge_context,
            known_types=", ".join(state.known_entity_types) or "(none yet)",
            instruction=state.pending_brief,
            revision_block=_revision_block(state),
            retry_feedback=retry_feedback,
        ),
    )
    return {
        "draft": result.value,
        "attempts": state.attempts + 1,
        "retry_feedback": "",
        "revision_feedback": "",
        "input_tokens": state.input_tokens + result.input_tokens,
        "output_tokens": state.output_tokens + result.output_tokens,
    }
