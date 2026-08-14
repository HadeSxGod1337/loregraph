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
from loregraph.schemas.agent import (
    AgentWarning,
    DraftEntity,
    DraftEntityPatch,
    GroundingReport,
    LoreDraft,
)
from loregraph.services.graph_query import edges_among
from loregraph.services.text_similarity import title_similarity
from loregraph.storage.protocols import EdgeStore, EntityStore, UsageStore

logger = logging.getLogger(__name__)

NODE = "validate_changes"

# Fuzzy title ratio above which a NEW entity is treated as a clone of an
# existing one — a routing slip the model should have made a patch instead.
DUPLICATE_TITLE_RATIO = 0.85
# How many times to bounce a duplicate-creating draft back with patch guidance
# before giving up and dropping the clone (never an endless loop).
MAX_GENERATION_ATTEMPTS = 2


async def validate_changes(
    state: AgentState,
    *,
    extraction: StructuredGenerator,
    token_budget: int,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    usage_store: UsageStore | None,
    model_name: str,
) -> dict[str, Any]:
    """The single guard between generation and review.

    Folds together everything that used to live in three separate nodes:
    duplicate detection over created entities, relationship-operation
    validation, patch-target validation, grounding-citation checks, and the
    optional LLM-as-judge grounding pass. Warnings never block — the DM sees
    them; the one thing that loops back is a NEW entity that clones an existing
    one, and only for a bounded number of attempts, with feedback that tells
    the model to PATCH it rather than 'use a different name'."""
    if state.draft is None:
        return {}
    draft = state.draft
    existing = await entity_store.list_entities(state.project_id)

    # ── Duplicate created entities → a patch was meant, not a create ──────────
    retry_texts, dup_warnings, cloned_refs = _detect_created_clones(
        draft.entities, existing
    )
    if retry_texts and state.attempts < MAX_GENERATION_ATTEMPTS:
        # Constructive retry: name the real id and tell it to patch, never
        # "invent different characters" (the old pressure that turned "edit
        # Егор" into two unrelated NPCs).
        return {
            "retry_feedback": (
                "These already exist — edit them with a patch instead of "
                "creating a copy: "
                + "; ".join(retry_texts)
                + ". Move each into `patches` (by its real id) or drop it, and "
                "keep only genuinely new things in `entities`."
            )
        }
    # Retries exhausted: drop the clones so an approve can't write a duplicate,
    # and let the warnings tell the DM what happened.
    kept_entities = [e for e in draft.entities if e.ref not in cloned_refs]

    warnings: list[AgentWarning] = list(dup_warnings)

    # ── Patch targets must be entities that actually exist ───────────────────
    existing_ids = {entity.id for entity in existing}
    kept_patches, patch_warnings = _validate_patches(draft.patches, existing_ids)
    warnings.extend(patch_warnings)

    # ── Relationship operations: endpoints and edge ids the model was shown ──
    refs = {entity.ref for entity in kept_entities}
    kept_rels, rel_warnings = validate_relationship_ops(
        draft.relationships,
        allowed_ends=refs | set(state.context_entity_ids),
        allowed_edge_ids=set(state.context_edge_ids),
    )
    warnings.extend(rel_warnings)
    warnings.extend(
        detect_relationship_conflicts(
            kept_rels,
            await edges_among(edge_store, state.project_id, state.context_entity_ids),
        )
    )

    # ── grounded_in citations must come from retrieval ───────────────────────
    allowed_citations = set(state.context_entity_ids)
    claimed: set[str] = set()
    for entity in kept_entities:
        claimed.update(entity.grounded_in)
    for patch in kept_patches:
        claimed.update(patch.grounded_in)
    for relationship in kept_rels:
        claimed.update(relationship.grounded_in)
    warnings.extend(
        AgentWarning(code="uncited_lore_id", params={"id": bad_id})
        for bad_id in sorted(claimed - allowed_citations)
    )

    draft = LoreDraft(
        entities=kept_entities, patches=kept_patches, relationships=kept_rels
    )
    update: dict[str, Any] = {"draft": draft, "attempts": state.attempts + 1}

    # ── LLM-as-judge grounding, narrowly scoped, budget-permitting ───────────
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
        checked = max(result.value.claims_checked, 0)
        flagged = min(max(result.value.claims_flagged, 0), checked)
        if checked:
            update["grounding_hallucination_rate"] = flagged / checked

    update["warnings"] = [*state.warnings, *warnings]
    return update


def _detect_created_clones(
    entities: list[DraftEntity], existing: list[Any]
) -> tuple[list[str], list[AgentWarning], set[str]]:
    """Created entities whose title collides with one that already exists.

    Returns (retry_texts, warnings, cloned_refs): the prose fed back to the
    generator, the structured warnings the DM would see, and the refs to drop
    once retries run out."""
    retry_texts: list[str] = []
    warnings: list[AgentWarning] = []
    cloned_refs: set[str] = set()
    for draft_entity in entities:
        title = draft_entity.title.casefold()
        for entity in existing:
            ratio = title_similarity(title, entity.title.casefold())
            if ratio >= DUPLICATE_TITLE_RATIO:
                retry_texts.append(
                    f"«{draft_entity.title}» = existing «{entity.title}» "
                    f"(id {entity.id})"
                )
                warnings.append(
                    AgentWarning(
                        code="duplicate_of_existing",
                        params={
                            "title": draft_entity.title,
                            "existing_title": entity.title,
                            "existing_id": entity.id,
                        },
                    )
                )
                cloned_refs.add(draft_entity.ref)
                break
    return retry_texts, warnings, cloned_refs


def _validate_patches(
    patches: list[DraftEntityPatch], existing_ids: set[str]
) -> tuple[list[DraftEntityPatch], list[AgentWarning]]:
    """A patch must target an entity that actually exists in this project; one
    that doesn't is dropped with a warning rather than silently reaching
    nothing at commit."""
    kept: list[DraftEntityPatch] = []
    warnings: list[AgentWarning] = []
    for patch in patches:
        if patch.entity_id in existing_ids:
            kept.append(patch)
        else:
            warnings.append(
                AgentWarning(
                    code="patch_unknown_entity",
                    params={"id": patch.entity_id},
                )
            )
    return kept, warnings


def route_after_validate(state: AgentState) -> str:
    """Loop back to generation only while a duplicate-creation retry is armed
    and the budget for it remains."""
    if state.retry_feedback and state.attempts < MAX_GENERATION_ATTEMPTS:
        return "retry"
    return "continue"
