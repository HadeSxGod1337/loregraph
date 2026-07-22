import logging
from typing import Any

from loregraph.agent.relationships import (
    detect_relationship_conflicts,
    validate_relationship_ops,
)
from loregraph.agent.state import NO_LORE_SENTINEL, AgentState
from loregraph.agent.usage import record_usage
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import render
from loregraph.schemas.agent import AgentWarning, GroundingReport, LoreDraft
from loregraph.services.graph_query import edges_among
from loregraph.storage.protocols import EdgeStore, UsageStore

logger = logging.getLogger(__name__)

NODE = "verify_grounding"


async def verify_grounding(
    state: AgentState,
    *,
    extraction: StructuredGenerator,
    token_budget: int,
    edge_store: EdgeStore,
    usage_store: UsageStore | None,
    model_name: str,
) -> dict[str, Any]:
    """Verifier before review. Deterministic part always runs: relationship
    operations must address entities and edges that retrieval actually
    returned (the model never gets to invent connection endpoints), and
    grounded_in citations must come from retrieval. The LLM-as-judge pass runs
    when there is lore to check against and budget left. Warnings never
    block — the DM sees them."""
    if state.draft is None:
        return {}
    warnings: list[AgentWarning] = []
    draft = state.draft

    # -- Deterministic: relationship operations.
    refs = {entity.ref for entity in draft.entities}
    kept, endpoint_warnings = validate_relationship_ops(
        draft.relationships,
        allowed_ends=refs | set(state.context_entity_ids),
        allowed_edge_ids=set(state.context_edge_ids),
    )
    warnings.extend(endpoint_warnings)
    if len(kept) != len(draft.relationships):
        draft = LoreDraft(entities=draft.entities, relationships=kept)

    # -- Deterministic: does this argue with the graph as it stands?
    warnings.extend(
        detect_relationship_conflicts(
            kept,
            await edges_among(edge_store, state.project_id, state.context_entity_ids),
        )
    )

    # -- Deterministic: citations must come from retrieval.
    allowed_citations = set(state.context_entity_ids)
    claimed: set[str] = set()
    for entity in draft.entities:
        claimed.update(entity.grounded_in)
    for relationship in draft.relationships:
        claimed.update(relationship.grounded_in)
    warnings.extend(
        AgentWarning(code="uncited_lore_id", params={"id": bad_id})
        for bad_id in sorted(claimed - allowed_citations)
    )

    update: dict[str, Any] = {"draft": draft}

    # -- LLM-as-judge, narrowly scoped to grounding. Free text in the lore's
    # language — not backend UI copy, wrapped as-is (code="llm_text").
    if state.existing_lore != NO_LORE_SENTINEL and not state.over_budget(token_budget):
        result = await extraction.generate(
            GroundingReport,
            system=render("verify_grounding.system.md"),
            user=render(
                "verify_grounding.user.md",
                existing_lore=state.existing_lore,
                draft=draft.model_dump_json(indent=2),
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
        warnings.extend(
            AgentWarning(code="llm_text", params={"text": text})
            for text in result.value.warnings
        )
        update["input_tokens"] = state.input_tokens + result.usage.input_tokens
        update["output_tokens"] = state.output_tokens + result.usage.output_tokens

        # Numeric counterpart to the free-text warnings above (CLAUDE.md,
        # "LLM для творчества, Python для арифметики"): the LLM judges which
        # claims are unsupported, Python turns that into a rate that can be
        # tracked/regressed across runs — clamped defensively since nothing
        # about the model's own count is schema-enforced to be consistent.
        checked = max(result.value.claims_checked, 0)
        flagged = min(max(result.value.claims_flagged, 0), checked)
        if checked:
            rate = flagged / checked
            logger.info(
                "verify_grounding hallucination_rate=%.3f (%d/%d claims flagged)",
                rate,
                flagged,
                checked,
            )
            update["grounding_hallucination_rate"] = rate

    update["warnings"] = [*state.warnings, *warnings]
    return update
