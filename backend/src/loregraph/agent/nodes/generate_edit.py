from typing import Any

from loregraph.agent.events import event_message
from loregraph.agent.state import AgentState
from loregraph.agent.usage import record_usage
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import project_instructions_block, render
from loregraph.schemas.agent import AgentWarning, EntityEditDraft
from loregraph.services.vector_index import entity_to_text
from loregraph.storage.protocols import EntityStore, ProjectStore, UsageStore

BUDGET_EXHAUSTED_WARNING = AgentWarning(code="budget_exhausted")

NODE = "generate_edit"


async def generate_edit(
    state: AgentState,
    *,
    creative: StructuredGenerator,
    token_budget: int,
    entity_store: EntityStore,
    project_store: ProjectStore,
    usage_store: UsageStore | None,
    model_name: str,
) -> dict[str, Any]:
    """One creative call produces a revised EntityEditDraft for the target
    entity. Reads the current entity from the store so the LLM always edits
    the actual live state, never a stale snapshot from the conversation.

    Write access deliberately absent — only commit() can call entity_service.
    """
    if state.over_budget(token_budget):
        return {
            "warnings": [*state.warnings, BUDGET_EXHAUSTED_WARNING],
            "retry_feedback": "",
            "attempts": state.attempts + 1,
        }

    if not state.pending_edit_entity_id:
        # Should never happen in a correctly wired graph, but surface it
        # gracefully rather than crashing.
        return {
            "messages": [
                event_message(
                    "Edit failed: no entity id was captured.",
                    "edit_failed",
                    reason="missing_entity_id",
                )
            ],
            "entity_edit_draft": None,
            "attempts": state.attempts + 1,
        }

    entities = await entity_store.get_many([state.pending_edit_entity_id])
    if not entities or entities[0].project_id != state.project_id:
        return {
            "messages": [
                event_message(
                    f"Edit failed: entity {state.pending_edit_entity_id} not found.",
                    "edit_failed",
                    reason="entity_not_found",
                )
            ],
            "entity_edit_draft": None,
            "attempts": state.attempts + 1,
        }

    entity = entities[0]
    project = await project_store.get(state.project_id)

    # Build compact available_links from recent entities (bounded, token-efficient)
    all_entities = await entity_store.list_entities(state.project_id)
    recent_entities = sorted(all_entities, key=lambda e: e.updated_at, reverse=True)[
        :20
    ]  # small bound — edit only needs a few link candidates
    available_links = "\n".join(f"{e.title} → {e.id}" for e in recent_entities)

    result = await creative.generate(
        EntityEditDraft,
        system=render(
            "edit_entity.system.md",
            project_instructions_block=project_instructions_block(
                project.agent_instructions
            ),
        ),
        cached_prefix=render(
            "edit_entity.user.md",
            current_entity=entity_to_text(entity),
            available_links=available_links or "(no entities in scope)",
            instruction=state.pending_brief,
        ),
        user="",
    )
    # Ensure the returned draft always carries the correct entity_id — the LLM
    # might hallucinate a different one if the prompt is unclear.
    draft = result.value
    draft.entity_id = state.pending_edit_entity_id

    await record_usage(
        usage_store,
        project_id=state.project_id,
        thread_id=state.thread_id,
        node=NODE,
        model=model_name,
        usage=result.usage,
    )
    return {
        "entity_edit_draft": draft,
        "attempts": state.attempts + 1,
        "input_tokens": state.input_tokens + result.usage.input_tokens,
        "output_tokens": state.output_tokens + result.usage.output_tokens,
    }
