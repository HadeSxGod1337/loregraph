import logging
from typing import Any

from langchain_core.messages import AIMessage

from loregraph.agent.state import AgentState
from loregraph.exceptions import CampaignError
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import EntityCreate, EntityFieldIn, FieldType
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService

logger = logging.getLogger(__name__)


async def commit(
    state: AgentState,
    *,
    entity_service: EntityService,
    edge_service: EdgeService,
) -> dict[str, Any]:
    """The only node with write access (structural HITL guarantee — no other
    node receives the services as an argument). Creates the whole approved
    batch: entities first (building the ref → real id map), then the
    relationship web. Idempotent per proposal via draft_committed. The chat
    acknowledgement is composed deterministically — zero extra LLM tokens."""
    if state.draft_committed:
        return {}
    if state.decision_action != "approve" or state.draft is None:
        # Reject: acknowledge in chat and clear the proposal.
        return {
            "messages": [AIMessage("Черновик отклонён — в мир ничего не записано.")],
            "draft": None,
            "warnings": [],
            "pending_brief": "",
        }

    warnings: list[str] = []
    ref_to_id: dict[str, str] = {}
    titles: list[str] = []
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

    edge_count = 0
    for relationship in state.draft.relationships:
        source_id = ref_to_id.get(relationship.source_ref)
        if source_id is None:
            continue  # source entity was removed by the DM at review
        # Target is either another draft entity (ref) or an existing entity id.
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
            # One bad edge must not lose the approved entities or other edges.
            logger.warning("Skipping approved relationship: %s", exc)
            warnings.append(
                f"Relationship {relationship.source_ref} → "
                f"{relationship.target_ref} failed: {exc}"
            )

    ack = (
        f"Готово — добавил в мир {len(titles)} "
        f"{'сущность' if len(titles) == 1 else 'сущностей'} "
        f"({', '.join(titles)}) и {edge_count} связей."
    )
    return {
        "messages": [AIMessage(ack)],
        "committed_entity_ids": [*state.committed_entity_ids, *ref_to_id.values()],
        "draft_committed": True,
        # Clear the proposal: smaller checkpoints, and the next propose_lore
        # starts clean. The review snapshot lives in the session registry.
        "draft": None,
        "warnings": warnings,
        "pending_brief": "",
    }
