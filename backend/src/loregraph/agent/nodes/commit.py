import asyncio
import logging
from typing import Any

from loregraph.agent.events import event_message
from loregraph.agent.state import AgentState
from loregraph.exceptions import CampaignError
from loregraph.schemas.agent import AgentWarning
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import EntityCreate, EntityFieldIn, EntityUpdate, FieldType
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService

logger = logging.getLogger(__name__)


async def _rollback_created(
    entity_service: EntityService, project_id: str, created_ids: list[str]
) -> None:
    """Best-effort compensation: each store.create() autocommits, so a
    mid-batch failure would otherwise leave a partial batch in the world and
    a retried approve would duplicate it."""
    for entity_id in created_ids:
        try:
            await entity_service.delete(project_id, entity_id)
        except Exception:
            logger.error(
                "Rollback of partially committed batch failed for entity %s",
                entity_id,
                exc_info=True,
            )


async def commit(
    state: AgentState,
    *,
    entity_service: EntityService,
    edge_service: EdgeService,
) -> dict[str, Any]:
    """The only node with write access (structural HITL guarantee — no other
    node receives the services as an argument). Creates the whole approved
    batch: entities first (building the ref → real id map), then the
    relationship web. All-or-nothing per proposal: a mid-batch failure rolls
    back the entities created so far, so a retry can't duplicate them.

    Acknowledgements are deterministic events (see agent/events.py) — zero
    extra LLM tokens, and language-agnostic: the UI translates the code, the
    English text is only for the model's own conversation history."""
    if state.draft_committed:
        return {}

    # ── Entity-edit path ──────────────────────────────────────────────────────
    if state.entity_edit_draft is not None:
        return await _commit_edit(
            state, entity_service=entity_service
        )

    # ── Batch-create path (propose_lore) ─────────────────────────────────────
    if state.decision_action != "approve" or state.draft is None:
        if state.draft is None and state.decision_action is None:
            # The pipeline produced no draft (e.g. token budget exhausted) —
            # tell the DM why instead of a misleading "rejected".
            reason_codes = ",".join(w.code for w in state.warnings)
            return {
                "messages": [
                    event_message(
                        "Couldn't produce a draft.",
                        "draft_failed",
                        reason_codes=reason_codes,
                    )
                ],
                "draft": None,
                "warnings": [],
                "pending_brief": "",
            }
        return {
            "messages": [
                event_message(
                    "Draft rejected — nothing was written to the world.",
                    "batch_rejected",
                )
            ],
            "draft": None,
            "warnings": [],
            "pending_brief": "",
        }

    warnings: list[AgentWarning] = []
    ref_to_id: dict[str, str] = {}
    titles: list[str] = []
    edge_count = 0
    try:
        for draft_entity in state.draft.entities:
            fields = [
                EntityFieldIn(
                    key="summary",
                    field_type=FieldType.TEXT,
                    value=draft_entity.summary,
                    show_on_card=True,
                ),
                *(
                    EntityFieldIn(
                        key=field.key, field_type=FieldType.TEXT, value=field.value
                    )
                    for field in draft_entity.fields
                ),
            ]
            entity = await entity_service.create(
                EntityCreate(
                    type=draft_entity.type, title=draft_entity.title, fields=fields
                ),
                state.project_id,
            )
            ref_to_id[draft_entity.ref] = entity.id
            titles.append(draft_entity.title)

        for relationship in state.draft.relationships:
            source_id = ref_to_id.get(relationship.source_ref)
            if source_id is None:
                continue  # source entity was removed by the DM at review
            # Target is either another draft entity (ref) or an existing id.
            target_id = ref_to_id.get(relationship.target_ref, relationship.target_ref)
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
                edge_count += 1
            except CampaignError as exc:
                # One bad edge must not lose the approved entities/edges.
                logger.warning("Skipping approved relationship: %s", exc)
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
    except asyncio.CancelledError:
        await _rollback_created(
            entity_service, state.project_id, list(ref_to_id.values())
        )
        raise
    except Exception:
        await _rollback_created(
            entity_service, state.project_id, list(ref_to_id.values())
        )
        raise

    return {
        "messages": [
            event_message(
                f"Committed {len(titles)} entities ({', '.join(titles)}) "
                f"and {edge_count} relationships.",
                "batch_committed",
                count=str(len(titles)),
                titles=", ".join(titles),
                edges=str(edge_count),
            )
        ],
        "committed_entity_ids": [*state.committed_entity_ids, *ref_to_id.values()],
        "draft_committed": True,
        # Clear the proposal: smaller checkpoints, and the next propose_lore
        # starts clean. The review snapshot lives in the session registry.
        "draft": None,
        "warnings": warnings,
        "pending_brief": "",
    }


async def _commit_edit(
    state: AgentState,
    *,
    entity_service: EntityService,
) -> dict[str, Any]:
    """Write path for the entity-edit pipeline.

    Applies the approved EntityEditDraft via entity_service.update so that
    project-scoping rules and vector re-indexing are enforced exactly as
    for REST / MCP writes.
    """
    if state.decision_action != "approve" or state.entity_edit_draft is None:
        return {
            "messages": [
                event_message(
                    "Edit rejected — nothing was written to the world.",
                    "batch_rejected",
                )
            ],
            "entity_edit_draft": None,
            "warnings": [],
            "pending_brief": "",
            "pending_edit_entity_id": "",
        }

    ed = state.entity_edit_draft
    fields = [
        EntityFieldIn(
            key="summary",
            field_type=FieldType.TEXT,
            value=ed.summary,
            show_on_card=True,
        ),
        *(
            EntityFieldIn(
                key=field.key, field_type=FieldType.TEXT, value=field.value
            )
            for field in ed.fields
        ),
    ]
    entity = await entity_service.update(
        state.project_id,
        ed.entity_id,
        EntityUpdate(type=ed.type, title=ed.title, fields=fields),
    )
    return {
        "messages": [
            event_message(
                f"Updated entity '{entity.title}'.",
                "entity_updated",
                entity_id=entity.id,
                title=entity.title,
            )
        ],
        "committed_entity_ids": [*state.committed_entity_ids, entity.id],
        "draft_committed": True,
        "entity_edit_draft": None,
        "warnings": [],
        "pending_brief": "",
        "pending_edit_entity_id": "",
    }
