"""Unit coverage for agent/relationships.py — the shared rules every
pipeline's relationship handling goes through, tested without a graph.

Also pins the schema's backward compatibility: drafts written before ops
existed live in checkpoints on disk and in the session registry, and they must
keep validating, or STATE_VERSION would have to be bumped and every
interrupted session on a user's machine would become unresumable.
"""

from datetime import UTC, datetime

from loregraph.agent.relationships import (
    detect_relationship_conflicts,
    validate_relationship_ops,
)
from loregraph.schemas.agent import DraftRelationship, LoreDraft
from loregraph.schemas.edge import EdgeOut


def edge(source: str, target: str, edge_type: str, edge_id: str = "e_1") -> EdgeOut:
    return EdgeOut(
        id=edge_id,
        project_id="p1",
        source_entity_id=source,
        target_entity_id=target,
        type=edge_type,
        label=None,
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Back-compat with drafts persisted before ops existed
# ---------------------------------------------------------------------------


def test_legacy_relationship_json_validates_as_a_create() -> None:
    legacy = {
        "source_ref": "e1",
        "target_ref": "npc_042",
        "type": "ally_of",
        "reason": "because",
        "grounded_in": [],
    }
    relationship = DraftRelationship.model_validate(legacy)
    assert relationship.op == "create"
    assert relationship.edge_id is None
    assert relationship.reverse is False


def test_legacy_draft_json_validates() -> None:
    legacy = {
        "entities": [
            {
                "ref": "e1",
                "type": "npc",
                "title": "Voss",
                "summary": "...",
                "fields": [],
                "grounded_in": [],
            }
        ],
        "relationships": [
            {
                "source_ref": "e1",
                "target_ref": "npc_042",
                "type": "ally_of",
                "reason": "because",
                "grounded_in": [],
            }
        ],
    }
    draft = LoreDraft.model_validate(legacy)
    assert draft.relationships[0].op == "create"


def test_draft_without_entities_is_valid() -> None:
    """ "Connect these two" is a complete proposal on its own."""
    draft = LoreDraft.model_validate({"relationships": []})
    assert draft.entities == []


# ---------------------------------------------------------------------------
# validate_relationship_ops
# ---------------------------------------------------------------------------


def test_both_endpoints_may_be_existing_entities() -> None:
    """The fix itself: a relationship between two entities that already exist
    used to be dropped on the source side."""
    kept, warnings = validate_relationship_ops(
        [DraftRelationship(source_ref="npc_a", target_ref="npc_b", type="ally_of")],
        allowed_ends={"npc_a", "npc_b"},
        allowed_edge_ids=set(),
    )
    assert len(kept) == 1
    assert warnings == []


def test_draft_ref_and_existing_id_mix_freely() -> None:
    kept, _ = validate_relationship_ops(
        [
            DraftRelationship(source_ref="e1", target_ref="npc_b", type="ally_of"),
            DraftRelationship(source_ref="npc_b", target_ref="e1", type="knows"),
        ],
        allowed_ends={"e1", "npc_b"},
        allowed_edge_ids=set(),
    )
    assert len(kept) == 2


def test_unknown_source_is_dropped() -> None:
    kept, warnings = validate_relationship_ops(
        [DraftRelationship(source_ref="ghost", target_ref="npc_b", type="ally_of")],
        allowed_ends={"npc_b"},
        allowed_edge_ids=set(),
    )
    assert kept == []
    assert [w.code for w in warnings] == ["dropped_unknown_source"]


def test_unknown_target_is_dropped() -> None:
    kept, warnings = validate_relationship_ops(
        [DraftRelationship(source_ref="npc_a", target_ref="ghost", type="ally_of")],
        allowed_ends={"npc_a"},
        allowed_edge_ids=set(),
    )
    assert kept == []
    assert [w.code for w in warnings] == ["dropped_unknown_target"]


def test_self_relationship_is_dropped() -> None:
    kept, warnings = validate_relationship_ops(
        [DraftRelationship(source_ref="npc_a", target_ref="npc_a", type="knows")],
        allowed_ends={"npc_a"},
        allowed_edge_ids=set(),
    )
    assert kept == []
    assert [w.code for w in warnings] == ["dropped_self_relationship"]


def test_update_and_delete_need_a_known_edge_id() -> None:
    kept, warnings = validate_relationship_ops(
        [
            DraftRelationship(op="update", edge_id="e_known", type="enemy_of"),
            DraftRelationship(op="delete", edge_id="e_unknown"),
            DraftRelationship(op="delete", edge_id=None),
        ],
        allowed_ends=set(),
        allowed_edge_ids={"e_known"},
    )
    assert len(kept) == 1
    assert kept[0].edge_id == "e_known"
    assert [w.code for w in warnings] == [
        "dropped_unknown_edge",
        "dropped_unknown_edge",
    ]


# ---------------------------------------------------------------------------
# detect_relationship_conflicts
# ---------------------------------------------------------------------------


def test_same_pair_different_type_conflicts() -> None:
    warnings = detect_relationship_conflicts(
        [DraftRelationship(source_ref="a", target_ref="b", type="enemy_of")],
        [edge("a", "b", "ally_of")],
    )
    assert [w.code for w in warnings] == ["conflicting_relationship"]
    assert warnings[0].params == {
        "existing_type": "ally_of",
        "proposed_type": "enemy_of",
    }


def test_conflict_detection_ignores_direction() -> None:
    """`A ally_of B` and `B ally_of A` are the same claim about the world."""
    warnings = detect_relationship_conflicts(
        [DraftRelationship(source_ref="b", target_ref="a", type="enemy_of")],
        [edge("a", "b", "ally_of")],
    )
    assert [w.code for w in warnings] == ["conflicting_relationship"]


def test_same_pair_same_type_is_a_duplicate() -> None:
    warnings = detect_relationship_conflicts(
        [DraftRelationship(source_ref="a", target_ref="b", type="ally_of")],
        [edge("a", "b", "ally_of")],
    )
    assert [w.code for w in warnings] == ["duplicate_relationship"]


def test_unrelated_pairs_do_not_conflict() -> None:
    warnings = detect_relationship_conflicts(
        [DraftRelationship(source_ref="a", target_ref="c", type="enemy_of")],
        [edge("a", "b", "ally_of")],
    )
    assert warnings == []


def test_update_and_delete_ops_never_conflict() -> None:
    """Only a new relationship can argue with an existing one; changing or
    removing that very relationship is the resolution, not the argument."""
    warnings = detect_relationship_conflicts(
        [
            DraftRelationship(op="update", edge_id="e_1", type="enemy_of"),
            DraftRelationship(op="delete", edge_id="e_1"),
        ],
        [edge("a", "b", "ally_of")],
    )
    assert warnings == []
