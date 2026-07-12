import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from loregraph.agent.state import AgentState
from loregraph.exceptions import CampaignError
from loregraph.schemas.edge import EdgeCreate
from loregraph.schemas.entity import EntityCreate, EntityFieldIn, FieldType
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService

logger = logging.getLogger(__name__)

# Deterministic chat acks — zero extra LLM tokens. Language follows the
# conversation (crude but honest heuristic: Cyrillic in the last user
# message → Russian), so the one hardcoded message in the system doesn't
# break the "reply in the GM's language" contract for non-Russian users.
ACK_COMMIT_RU = "Готово — добавил в мир {n} сущностей ({titles}) и {edges} связей."
ACK_COMMIT_EN = (
    "Done — added {n} entities to the world ({titles}) and {edges} relationships."
)
ACK_REJECT_RU = "Черновик отклонён — в мир ничего не записано."
ACK_REJECT_EN = "Draft rejected — nothing was written to the world."
ACK_NO_DRAFT_RU = "Не удалось подготовить черновик: {reasons}"
ACK_NO_DRAFT_EN = "Couldn't produce a draft: {reasons}"


def _is_russian(state: AgentState) -> bool:
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            return any("а" <= ch <= "я" or ch == "ё" for ch in message.content.lower())
    return False


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
    back the entities created so far, so a retry can't duplicate them."""
    if state.draft_committed:
        return {}
    russian = _is_russian(state)
    if state.decision_action != "approve" or state.draft is None:
        if state.draft is None and state.decision_action is None:
            # The pipeline produced no draft (e.g. token budget exhausted) —
            # tell the DM why instead of a misleading "rejected".
            template = ACK_NO_DRAFT_RU if russian else ACK_NO_DRAFT_EN
            ack = template.format(reasons="; ".join(state.warnings) or "unknown")
        else:
            ack = ACK_REJECT_RU if russian else ACK_REJECT_EN
        return {
            "messages": [AIMessage(ack)],
            "draft": None,
            "warnings": [],
            "pending_brief": "",
        }

    warnings: list[str] = []
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
                    f"Relationship {relationship.source_ref} → "
                    f"{relationship.target_ref} failed: {exc}"
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

    ack_template = ACK_COMMIT_RU if russian else ACK_COMMIT_EN
    return {
        "messages": [
            AIMessage(
                ack_template.format(
                    n=len(titles), titles=", ".join(titles), edges=edge_count
                )
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
