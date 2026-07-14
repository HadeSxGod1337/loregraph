from typing import Any

from loregraph.agent.state import AgentState
from loregraph.agent.usage import record_usage
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import project_instructions_block, render
from loregraph.schemas.agent import AgentWarning, LoreDraft
from loregraph.storage.protocols import ProjectStore, UsageStore

BUDGET_EXHAUSTED_WARNING = AgentWarning(code="budget_exhausted")

NODE = "generate_lore"


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


def _retry_block(state: AgentState) -> str:
    if not state.retry_feedback:
        return ""
    return f"\nIMPORTANT — previous attempt was rejected: {state.retry_feedback}"


async def generate_lore(
    state: AgentState,
    *,
    creative: StructuredGenerator,
    token_budget: int,
    project_store: ProjectStore,
    usage_store: UsageStore | None,
    model_name: str,
) -> dict[str, Any]:
    """One creative call produces a coherent batch: entities (types chosen by
    the model, steered toward the project's existing taxonomy) plus the
    relationship web between them and to existing lore."""
    if state.over_budget(token_budget):
        # Never silently burn the user's key past the ceiling: surface the
        # stop at review instead.
        # retry_feedback is cleared AND attempts advanced: check_duplicates_
        # draft re-arms retry_feedback for the unchanged draft, so without
        # the attempts bump the generate↔check cycle would loop forever.
        return {
            "warnings": [*state.warnings, BUDGET_EXHAUSTED_WARNING],
            "retry_feedback": "",
            "attempts": state.attempts + 1,
        }

    project = await project_store.get(state.project_id)
    # Split into a stable prefix and a volatile tail so prompt caching can
    # work: retrieved lore, the knowledge base, the taxonomy and the brief are
    # identical across every regeneration of this proposal (collision retry,
    # review revision), while the revision/retry directives are what changed.
    # The generator puts the cache breakpoint on the prefix (see
    # llm/structured.py) — regenerations then re-read it instead of re-paying.
    cached_prefix = render(
        "generate_lore.user.md",
        existing_lore=state.existing_lore,
        knowledge_context=state.knowledge_context,
        known_types=", ".join(state.known_entity_types) or "(none yet)",
        instruction=state.pending_brief,
    )
    volatile = "\n".join(
        part for part in (_revision_block(state), _retry_block(state)) if part
    )
    result = await creative.generate(
        LoreDraft,
        system=render(
            "generate_lore.system.md",
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
