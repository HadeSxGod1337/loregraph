from typing import Any

from loregraph.agent.relationships import (
    detect_relationship_conflicts,
    validate_relationship_ops,
)
from loregraph.agent.state import AgentState
from loregraph.agent.usage import record_usage
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import project_instructions_block, render
from loregraph.schemas.agent import AgentWarning, LoreDraft
from loregraph.schemas.edge import EdgeOut
from loregraph.schemas.entity import EntityOut
from loregraph.services.graph_query import edges_among
from loregraph.storage.protocols import EdgeStore, EntityStore, ProjectStore, UsageStore

BUDGET_EXHAUSTED_WARNING = AgentWarning(code="budget_exhausted")

NODE = "generate_relationships"


async def generate_relationships(
    state: AgentState,
    *,
    extraction: StructuredGenerator,
    token_budget: int,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    project_store: ProjectStore,
    usage_store: UsageStore | None,
    model_name: str,
) -> dict[str, Any]:
    """Turns "connect these two" into relationship operations for review.

    Runs on the extraction tier, not the creative one: mapping a request onto
    a fixed vocabulary of ops over entities that already exist is
    classification, and CLAUDE.md puts that on the cheap model at a low
    temperature. That is also why this skill exists next to propose_lore
    rather than inside it — the same request through the creative pipeline
    pays for retrieval, deduplication and a much larger prompt.

    Scope comes from the entity ids the assistant passed, so the model only
    ever sees what the game master pointed at. It validates against what it
    just read rather than deferring to verify_grounding: the whitelist here is
    exact, so the pipeline goes straight to review.

    Write access deliberately absent — only commit() can call edge_service.
    """
    if state.over_budget(token_budget):
        return {
            "warnings": [*state.warnings, BUDGET_EXHAUSTED_WARNING],
            "attempts": state.attempts + 1,
        }

    entities = await _entities_in_scope(state, entity_store)
    if len(entities) < 2:
        # Nothing to wire: either the assistant passed too few ids, or they
        # belong to another project. Leaving the draft None takes the
        # pipeline through human_review's empty-content check straight to
        # commit, which reports the warning codes to the chat — no second
        # event of our own competing with that one.
        return {
            "draft": None,
            "warnings": [
                *state.warnings,
                AgentWarning(code="relationship_scope_empty"),
            ],
            "attempts": state.attempts + 1,
        }

    entity_ids = [entity.id for entity in entities]
    existing_edges = await edges_among(edge_store, state.project_id, entity_ids)
    title_by_id = {entity.id: entity.title for entity in entities}
    project = await project_store.get(state.project_id)

    result = await extraction.generate(
        LoreDraft,
        system=render(
            "manage_relationships.system.md",
            project_instructions_block=project_instructions_block(
                project.agent_instructions
            ),
        ),
        user=render(
            "manage_relationships.user.md",
            entities_in_scope="\n".join(_entity_line(entity) for entity in entities),
            existing_relationships=(
                "\n".join(_edge_line(edge, title_by_id) for edge in existing_edges)
                or "(these entities are not connected to each other yet)"
            ),
            instruction=state.pending_brief,
        ),
    )
    await record_usage(
        usage_store,
        project_id=state.project_id,
        thread_id=state.thread_id,
        node=NODE,
        model=model_name,
        usage=result.usage,
    )

    warnings: list[AgentWarning] = []
    # This node wires, it does not write lore. An entity that slipped through
    # is dropped rather than quietly committed as a side effect of asking for
    # a connection — that is the bug this whole skill exists to end.
    if result.value.entities:
        warnings.extend(
            AgentWarning(code="dropped_draft_entity", params={"title": entity.title})
            for entity in result.value.entities
        )

    kept, op_warnings = validate_relationship_ops(
        result.value.relationships,
        allowed_ends=set(entity_ids),
        allowed_edge_ids={edge.id for edge in existing_edges},
    )
    warnings.extend(op_warnings)
    warnings.extend(detect_relationship_conflicts(kept, existing_edges))

    return {
        "draft": LoreDraft(entities=[], relationships=kept),
        # Mirrors what the model was shown, so a revise round trip through
        # verify_grounding validates against the same whitelist this node used.
        "context_entity_ids": entity_ids,
        "context_edge_ids": [edge.id for edge in existing_edges],
        "warnings": [*state.warnings, *warnings],
        "attempts": state.attempts + 1,
        "input_tokens": state.input_tokens + result.usage.input_tokens,
        "output_tokens": state.output_tokens + result.usage.output_tokens,
    }


async def _entities_in_scope(
    state: AgentState, entity_store: EntityStore
) -> list[EntityOut]:
    """The requested entities that actually exist in this project — cross-
    project ids are dropped silently, the same way retrieval never leaks
    another world's entities into a prompt."""
    if not state.pending_entity_ids:
        return []
    entities = await entity_store.get_many(state.pending_entity_ids)
    return [entity for entity in entities if entity.project_id == state.project_id]


def _entity_line(entity: EntityOut) -> str:
    return f'<entity id="{entity.id}" type="{entity.type}">{entity.title}</entity>'


def _edge_line(edge: EdgeOut, title_by_id: dict[str, str]) -> str:
    source = title_by_id.get(edge.source_entity_id, edge.source_entity_id)
    target = title_by_id.get(edge.target_entity_id, edge.target_entity_id)
    label = f" ({edge.label})" if edge.label else ""
    return (
        f'<relationship id="{edge.id}">'
        f"{source} --{edge.type}--> {target}{label}</relationship>"
    )
