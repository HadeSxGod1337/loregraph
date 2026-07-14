from typing import Any

from loregraph.agent.state import NO_LORE_SENTINEL, AgentState
from loregraph.agent.usage import record_usage
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import render
from loregraph.schemas.agent import AgentWarning, GroundingReport, LoreDraft
from loregraph.storage.protocols import UsageStore

NODE = "verify_grounding"


async def verify_grounding(
    state: AgentState,
    *,
    extraction: StructuredGenerator,
    token_budget: int,
    usage_store: UsageStore | None,
    model_name: str,
) -> dict[str, Any]:
    """Verifier before review. Deterministic part always runs: relationship
    endpoints must be real draft refs or retrieved entity ids (the model
    never gets to invent connection targets), and grounded_in citations must
    come from retrieval. The LLM-as-judge pass runs when there is lore to
    check against and budget left. Warnings never block — the DM sees them."""
    if state.draft is None:
        return {}
    warnings: list[AgentWarning] = []
    draft = state.draft

    # -- Deterministic: relationship endpoints.
    refs = {entity.ref for entity in draft.entities}
    allowed_targets = refs | set(state.context_entity_ids)
    kept = []
    for relationship in draft.relationships:
        if relationship.source_ref not in refs:
            warnings.append(
                AgentWarning(
                    code="dropped_unknown_source",
                    params={"ref": relationship.source_ref},
                )
            )
        elif relationship.target_ref not in allowed_targets:
            warnings.append(
                AgentWarning(
                    code="dropped_unknown_target",
                    params={"ref": relationship.target_ref},
                )
            )
        else:
            kept.append(relationship)
    if len(kept) != len(draft.relationships):
        draft = LoreDraft(entities=draft.entities, relationships=kept)

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

    update["warnings"] = [*state.warnings, *warnings]
    return update
