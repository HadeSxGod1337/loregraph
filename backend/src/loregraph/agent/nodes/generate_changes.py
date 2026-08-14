from typing import Any

from loregraph.agent.state import AgentState
from loregraph.agent.usage import record_usage
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import project_instructions_block, render
from loregraph.schemas.agent import AgentWarning, LoreDraft
from loregraph.storage.protocols import ProjectStore, UsageStore

BUDGET_EXHAUSTED_WARNING = AgentWarning(code="budget_exhausted")

NODE = "generate_changes"


def _revision_block(state: AgentState) -> str:
    """When the DM asked for changes at review, revise the current draft
    instead of regenerating from scratch — cheaper and keeps what they liked."""
    if not state.revision_feedback or state.draft is None:
        return ""
    return (
        "\nYou are REVISING your previous proposal. Keep everything the game "
        "master did not criticize (same refs, same titles, same patches), "
        "change only what the feedback asks for.\n"
        f"<previous_proposal>\n{state.draft.model_dump_json()}\n</previous_proposal>\n"
        f"<feedback>\n{state.revision_feedback}\n</feedback>"
    )


def _retry_block(state: AgentState) -> str:
    if not state.retry_feedback:
        return ""
    return f"\nIMPORTANT — fix this before proposing again: {state.retry_feedback}"


async def generate_changes(
    state: AgentState,
    *,
    creative: StructuredGenerator,
    token_budget: int,
    project_store: ProjectStore,
    usage_store: UsageStore | None,
    model_name: str,
) -> dict[str, Any]:
    """One creative call produces a whole proposal — new entities, patches to
    existing ones, and relationship operations — in a single coherent pass.

    This is the one write-generation node: create, edit and link all flow
    through it, so "improve Егор and connect him to the Тень" is one proposal,
    not three tools the model has to choose between up front. Write access is
    deliberately absent; only commit() touches the stores."""
    if state.over_budget(token_budget):
        # Never silently burn the user's key past the ceiling: surface the
        # stop at review instead. retry_feedback cleared AND attempts advanced
        # so the generate↔validate cycle cannot loop forever.
        return {
            "warnings": [*state.warnings, BUDGET_EXHAUSTED_WARNING],
            "retry_feedback": "",
            "attempts": state.attempts + 1,
        }

    project = await project_store.get(state.project_id)
    # Stable prefix (retrieved lore, targets, taxonomy, brief) vs. volatile
    # tail (revision/retry directives) so prompt caching reuses the prefix
    # across every regeneration of this proposal — see llm/structured.py.
    cached_prefix = render(
        "propose_changes.user.md",
        existing_lore=state.existing_lore,
        targets=state.targets_block or "(none — this request names no existing "
        "entity to edit)",
        knowledge_context=state.knowledge_context,
        known_types=", ".join(state.known_entity_types) or "(none yet)",
        available_links=state.available_links or "(no entities in scope)",
        instruction=state.pending_brief,
    )
    volatile = "\n".join(
        part for part in (_revision_block(state), _retry_block(state)) if part
    )
    result = await creative.generate(
        LoreDraft,
        system=render(
            "propose_changes.system.md",
            project_instructions_block=project_instructions_block(
                project.agent_instructions
            ),
        ),
        cached_prefix=cached_prefix,
        user=volatile,
    )
    await record_usage(
        usage_store,
        project_id=state.project_id,
        thread_id=state.thread_id,
        node=NODE,
        model=model_name,
        usage=result.usage,
    )
    return {
        "draft": result.value,
        "attempts": state.attempts + 1,
        "retry_feedback": "",
        "revision_feedback": "",
        "input_tokens": state.input_tokens + result.usage.input_tokens,
        "output_tokens": state.output_tokens + result.usage.output_tokens,
    }
