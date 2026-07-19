import asyncio
import logging
from typing import Any

from loregraph.agent.import_state import ImportState
from loregraph.agent.nodes.commit import (
    _build_fields,
    _build_title_to_id,
    _rollback_created,
)
from loregraph.exceptions import CampaignError
from loregraph.schemas.agent import AgentWarning
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import EntityCreate
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService

logger = logging.getLogger(__name__)

NODE_COMMIT = "import_commit_slice"
NODE_RELATIONSHIPS = "import_commit_relationships"


async def commit_slice(
    state: ImportState, *, entity_service: EntityService
) -> dict[str, Any]:
    """Writes the current review page's entities. Only reached (via
    route_after_slice_review / route_after_advance) when the DM's decision
    for this page was approve/approve_all — reject never routes here.
    Reuses commit.py's low-level helpers (title->id map, wikilink-to-
    ProseMirror conversion) so entity creation behaves identically to the
    chat pipeline's batch commit."""
    slice_draft = state.review_slices[state.current_slice]
    title_to_id = await _build_title_to_id(entity_service, state.project_id)
    new_ref_to_id: dict[str, str] = {}
    created_ids: list[str] = []
    try:
        for draft_entity in slice_draft.entities:
            fields = _build_fields(draft_entity, title_to_id)
            entity = await entity_service.create(
                EntityCreate(
                    type=draft_entity.type, title=draft_entity.title, fields=fields
                ),
                state.project_id,
            )
            new_ref_to_id[draft_entity.ref] = entity.id
            title_to_id[draft_entity.title.lower()] = entity.id
            created_ids.append(entity.id)
    except asyncio.CancelledError:
        await _rollback_created(entity_service, state.project_id, created_ids)
        raise
    except Exception:
        await _rollback_created(entity_service, state.project_id, created_ids)
        raise
    return {
        "committed_entity_ids": [*state.committed_entity_ids, *created_ids],
        "ref_to_id": {**state.ref_to_id, **new_ref_to_id},
    }


def advance_slice(state: ImportState) -> dict[str, Any]:
    return {"current_slice": state.current_slice + 1}


def route_after_advance(state: ImportState) -> str:
    if state.current_slice >= len(state.review_slices):
        return "relationships"
    if state.decision_action == "approve_all":
        # Real "approve all remaining" — every subsequent page still goes
        # through commit_slice's own write path, just without another
        # interrupt asking the DM to look at it again (see
        # agent/nodes/import_review.py's ImportReviewDecision docstring).
        return "commit"
    return "review"


async def commit_relationships(
    state: ImportState, *, edge_service: EdgeService
) -> dict[str, Any]:
    """Final node: every entity page has been resolved (approved, edited,
    or rejected), so every ref that WILL ever get a real id is already in
    ImportState.ref_to_id. Relationships commit here in one pass rather
    than per-page because a relationship may point at an entity from a
    later page that hadn't committed yet when an earlier page was written.
    A relationship whose endpoint was on a rejected page (never in
    ref_to_id, and not an existing entity id either) fails at the edge
    service and is dropped with a warning — the same per-edge tolerance as
    commit.py's batch-create path."""
    warnings = list(state.warnings)
    for relationship in state.pending_relationships:
        source_id = state.ref_to_id.get(
            relationship.source_ref, relationship.source_ref
        )
        target_id = state.ref_to_id.get(
            relationship.target_ref, relationship.target_ref
        )
        try:
            await edge_service.create(
                state.project_id,
                EdgeCreate(
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    type=relationship.type,
                    label=relationship.reason or None,
                ),
            )
        except CampaignError as exc:
            logger.warning("Skipping unresolved import relationship: %s", exc)
            warnings.append(
                AgentWarning(
                    code="relationship_failed",
                    params={
                        "source": relationship.source_ref,
                        "target": relationship.target_ref,
                        "detail": str(exc),
                    },
                )
            )
    return {"warnings": warnings}
