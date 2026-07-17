"""Golden cases for run_hallucination_eval.py.

Each case is a LoreDraft plus the retrieval context it was (hypothetically)
generated from, labeled clean (fully grounded — should produce zero
grounding warnings) or poisoned (contains a fabricated grounded_in citation
or a relationship pointing at an entity that was never retrieved/drafted —
the shape a real LLM hallucination takes). The eval measures how much of the
poisoning agent/nodes/verify_grounding.py's deterministic checks actually
catch, and whether clean drafts ever trip a false positive.
"""

from dataclasses import dataclass

from loregraph.schemas.agent import DraftEntity, DraftRelationship, LoreDraft


@dataclass(frozen=True)
class HallucinationCase:
    case_id: str
    context_entity_ids: list[str]  # what retrieval actually returned
    draft: LoreDraft
    poisoned_claim_count: int  # fabricated grounded_in/relationship claims planted


CASES: list[HallucinationCase] = [
    HallucinationCase(
        case_id="clean_single_citation",
        context_entity_ids=["npc_mira"],
        draft=LoreDraft(
            entities=[
                DraftEntity(
                    ref="e1",
                    type="npc",
                    title="Guard Captain Voss",
                    summary="A guard captain recruited by Mira's guild.",
                    grounded_in=["npc_mira"],
                ),
            ],
        ),
        poisoned_claim_count=0,
    ),
    HallucinationCase(
        case_id="clean_relationship_to_retrieved_entity",
        context_entity_ids=["npc_mira", "faction_guild"],
        draft=LoreDraft(
            entities=[
                DraftEntity(
                    ref="e1",
                    type="npc",
                    title="Voss",
                    summary="...",
                    grounded_in=["npc_mira"],
                ),
            ],
            relationships=[
                DraftRelationship(
                    source_ref="e1",
                    target_ref="faction_guild",
                    type="member_of",
                    reason="Recruited alongside Mira.",
                    grounded_in=["faction_guild"],
                ),
            ],
        ),
        poisoned_claim_count=0,
    ),
    HallucinationCase(
        case_id="fabricated_citation",
        context_entity_ids=["npc_mira"],
        draft=LoreDraft(
            entities=[
                DraftEntity(
                    ref="e1",
                    type="npc",
                    title="Voss",
                    summary="...",
                    # npc_ghost_003 was never retrieved — fabricated citation.
                    grounded_in=["npc_mira", "npc_ghost_003"],
                ),
            ],
        ),
        poisoned_claim_count=1,
    ),
    HallucinationCase(
        case_id="dangling_relationship_target",
        context_entity_ids=["npc_mira"],
        draft=LoreDraft(
            entities=[DraftEntity(ref="e1", type="npc", title="Voss", summary="...")],
            relationships=[
                DraftRelationship(
                    # faction_shadow_099 is neither a draft ref nor a
                    # retrieved entity — invented on the spot.
                    source_ref="e1",
                    target_ref="faction_shadow_099",
                    type="enemy_of",
                    reason="invented on the spot",
                ),
            ],
        ),
        poisoned_claim_count=1,
    ),
    HallucinationCase(
        case_id="unknown_source_ref",
        context_entity_ids=["npc_mira"],
        draft=LoreDraft(
            entities=[DraftEntity(ref="e1", type="npc", title="Voss", summary="...")],
            relationships=[
                DraftRelationship(
                    # e_typo_ref matches no draft entity's ref.
                    source_ref="e_typo_ref",
                    target_ref="e1",
                    type="ally_of",
                    reason="ref typo / hallucinated source",
                ),
            ],
        ),
        poisoned_claim_count=1,
    ),
    HallucinationCase(
        case_id="double_poisoned_entity",
        context_entity_ids=["npc_mira"],
        draft=LoreDraft(
            entities=[
                DraftEntity(
                    ref="e1",
                    type="npc",
                    title="Voss",
                    summary="...",
                    grounded_in=["npc_ghost_003"],
                ),
            ],
            relationships=[
                DraftRelationship(
                    source_ref="e1",
                    target_ref="faction_shadow_099",
                    type="enemy_of",
                    reason="two hallucinations in one draft",
                ),
            ],
        ),
        poisoned_claim_count=2,
    ),
]
