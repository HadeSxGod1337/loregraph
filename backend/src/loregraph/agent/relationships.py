"""Validation and write path for proposed relationship operations.

One module for everything that turns a DraftRelationship into a change in the
graph, shared by every node that touches one: verify_grounding and
generate_relationships validate, commit and import_commit apply. Keeping the
two halves together is what stops the endpoint rules from drifting apart again
— the create path used to accept an existing entity as a relationship's target
but not as its source, in three places with three separate copies of the rule.

`apply_relationship_ops` takes the EdgeService as an argument rather than
reaching for one: the structural HITL guarantee is that only commit nodes hold
a write service, and that stays true when the helper they call is here.
"""

import logging
from dataclasses import dataclass, field

from loregraph.exceptions import CampaignError
from loregraph.schemas.agent import AgentWarning, DraftRelationship
from loregraph.schemas.edge import EdgeCreate, EdgeOut, EdgeUpdate
from loregraph.services.edge_service import EdgeService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelationshipOpsResult:
    """Outcome of applying one draft's relationship operations."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
    warnings: list[AgentWarning] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.deleted


def validate_relationship_ops(
    relationships: list[DraftRelationship],
    *,
    allowed_ends: set[str],
    allowed_edge_ids: set[str],
) -> tuple[list[DraftRelationship], list[AgentWarning]]:
    """Split proposed operations into the ones that may reach the DM and the
    ones the model made up, with a warning for each rejection.

    `allowed_ends` are the entity references a create may connect: refs from
    this same draft plus the ids retrieval actually returned. Both endpoints
    are checked against it — a relationship between two entities that already
    exist is a legitimate proposal, and rejecting it on the source side is
    what used to push the model into inventing a throwaway entity to hang the
    edge on. `allowed_edge_ids` are the relationships the model was shown, so
    an update/delete can only address something it actually saw.

    Warnings, never exceptions: a rejected op is information for the DM, not a
    reason to fail the run."""
    kept: list[DraftRelationship] = []
    warnings: list[AgentWarning] = []

    for relationship in relationships:
        if relationship.op == "create":
            if relationship.source_ref not in allowed_ends:
                warnings.append(
                    AgentWarning(
                        code="dropped_unknown_source",
                        params={"ref": relationship.source_ref},
                    )
                )
            elif relationship.target_ref not in allowed_ends:
                warnings.append(
                    AgentWarning(
                        code="dropped_unknown_target",
                        params={"ref": relationship.target_ref},
                    )
                )
            elif relationship.source_ref == relationship.target_ref:
                warnings.append(
                    AgentWarning(
                        code="dropped_self_relationship",
                        params={"ref": relationship.source_ref},
                    )
                )
            else:
                kept.append(relationship)
            continue

        # update / delete address an existing edge by id.
        if not relationship.edge_id or relationship.edge_id not in allowed_edge_ids:
            warnings.append(
                AgentWarning(
                    code="dropped_unknown_edge",
                    params={"ref": relationship.edge_id or "", "op": relationship.op},
                )
            )
        else:
            kept.append(relationship)

    return kept, warnings


def detect_relationship_conflicts(
    relationships: list[DraftRelationship],
    existing_edges: list[EdgeOut],
) -> list[AgentWarning]:
    """Warn when a proposed relationship argues with one the world already
    has: the same pair already typed differently, or the same pair typed
    identically.

    The model has no memory across sessions, so left alone it will happily
    propose `enemy_of` over a pair it made `ally_of` last week. Deliberately a
    warning and not a rejection — a falling-out is a legitimate story beat,
    and only the DM can tell that from a contradiction. Direction is ignored
    when pairing: `A ally_of B` and `B ally_of A` are the same claim."""
    by_pair: dict[frozenset[str], list[EdgeOut]] = {}
    for edge in existing_edges:
        pair = frozenset({edge.source_entity_id, edge.target_entity_id})
        by_pair.setdefault(pair, []).append(edge)

    warnings: list[AgentWarning] = []
    for relationship in relationships:
        if relationship.op != "create":
            continue
        pair = frozenset({relationship.source_ref, relationship.target_ref})
        for edge in by_pair.get(pair, []):
            if edge.type == relationship.type:
                warnings.append(
                    AgentWarning(
                        code="duplicate_relationship",
                        params={"type": edge.type},
                    )
                )
            else:
                warnings.append(
                    AgentWarning(
                        code="conflicting_relationship",
                        params={
                            "existing_type": edge.type,
                            "proposed_type": relationship.type,
                        },
                    )
                )
    return warnings


async def apply_relationship_ops(
    relationships: list[DraftRelationship],
    *,
    edge_service: EdgeService,
    project_id: str,
    ref_to_id: dict[str, str],
) -> RelationshipOpsResult:
    """Write approved relationship operations, tolerating a bad one.

    Ordered create → update → delete on purpose: deletion is the only step
    that cannot be compensated. The batch rollback in commit.py restores
    entities it created, and a re-created edge would come back with a new id,
    so nothing destructive runs until everything that might still fail has
    succeeded.

    `ref_to_id` maps this draft's refs to the ids they were just written
    under; an endpoint that is not in it is passed through as-is, which is how
    an existing entity's id ends up on either side of a new relationship."""
    created = updated = deleted = 0
    warnings: list[AgentWarning] = []

    def _failed(relationship: DraftRelationship, exc: Exception) -> None:
        logger.warning("Skipping approved relationship op: %s", exc)
        warnings.append(
            AgentWarning(
                code="relationship_failed",
                params={
                    "op": relationship.op,
                    "source": relationship.source_ref or (relationship.edge_id or ""),
                    "target": relationship.target_ref,
                    "detail": str(exc),
                },
            )
        )

    for relationship in (r for r in relationships if r.op == "create"):
        source_id = ref_to_id.get(relationship.source_ref, relationship.source_ref)
        target_id = ref_to_id.get(relationship.target_ref, relationship.target_ref)
        try:
            await edge_service.create(
                project_id,
                EdgeCreate(
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    type=relationship.type,
                    label=relationship.reason or None,
                ),
            )
            created += 1
        except CampaignError as exc:
            _failed(relationship, exc)

    for relationship in (r for r in relationships if r.op == "update"):
        edge_id = relationship.edge_id or ""
        try:
            # EdgeUpdate replaces rather than patches, so anything the model
            # left out has to be carried over from the edge as it stands —
            # otherwise a "just reverse it" op would blank the type and label.
            current = await edge_service.get_in_project(project_id, edge_id)
            await edge_service.update(
                project_id,
                edge_id,
                EdgeUpdate(
                    type=relationship.type or current.type,
                    label=relationship.reason or current.label,
                    reverse=relationship.reverse,
                ),
            )
            updated += 1
        except CampaignError as exc:
            _failed(relationship, exc)

    for relationship in (r for r in relationships if r.op == "delete"):
        try:
            await edge_service.delete(project_id, relationship.edge_id or "")
            deleted += 1
        except CampaignError as exc:
            _failed(relationship, exc)

    return RelationshipOpsResult(
        created=created, updated=updated, deleted=deleted, warnings=warnings
    )
