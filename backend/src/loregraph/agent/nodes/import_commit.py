import asyncio
import logging
from typing import Any

from loregraph.agent.import_state import ImportState
from loregraph.agent.nodes.commit import (
    _build_fields,
    _build_title_to_id,
    _rollback_created,
)
from loregraph.agent.relationships import apply_relationship_ops
from loregraph.schemas.entity import EntityCreate, EntityFieldIn, FieldType
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
            provenance = _provenance_field(state)
            if provenance is not None:
                fields.append(provenance)
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


def _provenance_field(state: ImportState) -> EntityFieldIn | None:
    """Coarse "where did this come from" marker on migrated entities.

    Deliberately a plain field, NOT a ConnectionEntityLink: the AI extractor
    merges and splits content across windows, so there is no honest 1:1
    external_id↔entity mapping to record (that mapping is what the
    deterministic Exporter/Importer round-trip relies on). Migration is
    therefore one-directional — a later export to that same tool creates
    fresh, properly linked records rather than round-tripping these."""
    if state.source_kind != "connection" or not state.source_filename:
        return None
    return EntityFieldIn(
        key="source",
        field_type=FieldType.TEXT,
        value=f"Migrated from {state.source_filename}",
    )


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
    service and is dropped with a warning — the same per-edge tolerance the
    shared write path gives every other pipeline."""
    ops = await apply_relationship_ops(
        state.pending_relationships,
        edge_service=edge_service,
        project_id=state.project_id,
        ref_to_id=state.ref_to_id,
    )
    return {"warnings": [*state.warnings, *ops.warnings]}
