import asyncio
import logging
import re
from typing import Any

from loregraph.agent.events import event_message
from loregraph.agent.relationships import apply_relationship_ops
from loregraph.agent.state import AgentState
from loregraph.schemas.agent import DraftEntity, EntityEditDraft
from loregraph.schemas.entity import (
    EntityCreate,
    EntityFieldIn,
    EntityUpdate,
    FieldType,
)
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService

logger = logging.getLogger(__name__)

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _wikilinks_to_prosemirror(text: str, title_to_id: dict[str, str]) -> dict[str, Any]:
    """Convert text with ``[[label]]`` wikilinks to a ProseMirror doc containing
    ``entityLink`` nodes.  Unresolved labels (no matching entity) are left as
    plain text so the doc never breaks."""
    paragraphs = text.split("\n\n")
    doc_content: list[dict[str, Any]] = []

    for para_text in paragraphs:
        if not para_text.strip():
            continue
        # Handle single newlines within a paragraph as hard breaks
        lines = para_text.split("\n")
        para_content: list[dict[str, Any]] = []

        for i, line in enumerate(lines):
            if i > 0:
                para_content.append({"type": "hardBreak"})
            last_end = 0
            for match in _WIKILINK_RE.finditer(line):
                if match.start() > last_end:
                    para_content.append(
                        {"type": "text", "text": line[last_end : match.start()]}
                    )
                label = match.group(1)
                entity_id = title_to_id.get(label.lower(), "")
                para_content.append(
                    {
                        "type": "entityLink",
                        "attrs": {
                            "entityId": entity_id,
                            "fieldKey": None,
                            "label": label,
                        },
                    }
                )
                last_end = match.end()
            if last_end < len(line):
                para_content.append({"type": "text", "text": line[last_end:]})

        if para_content:
            doc_content.append({"type": "paragraph", "content": para_content})

    if not doc_content:
        doc_content.append({"type": "paragraph", "content": []})

    return {"type": "doc", "content": doc_content}


async def _build_title_to_id(
    entity_service: EntityService,
    project_id: str,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a case-insensitive title→id map from existing entities, merged
    with any ``extra`` mappings (e.g. batch entities created so far)."""
    all_entities = await entity_service.list_entities(project_id)
    title_to_id: dict[str, str] = {
        entity.title.lower(): entity.id for entity in all_entities
    }
    if extra:
        title_to_id.update({k.lower(): v for k, v in extra.items()})
    return title_to_id


def _build_fields(
    draft_entity: DraftEntity | EntityEditDraft,
    title_to_id: dict[str, str],
) -> list[EntityFieldIn]:
    """Build EntityFieldIn list from a draft entity, converting rich_text
    fields that contain ``[[label]]`` wikilinks to ProseMirror docs."""
    fields: list[EntityFieldIn] = [
        EntityFieldIn(
            key="summary",
            field_type=FieldType.TEXT,
            value=draft_entity.summary,
            show_on_card=True,
        ),
    ]
    for field in draft_entity.fields:
        if getattr(field, "field_type", FieldType.TEXT) == FieldType.RICH_TEXT:
            prosemirror = _wikilinks_to_prosemirror(field.value, title_to_id)
            fields.append(
                EntityFieldIn(
                    key=field.key,
                    field_type=FieldType.RICH_TEXT,
                    value=prosemirror,
                )
            )
        else:
            fields.append(
                EntityFieldIn(
                    key=field.key,
                    field_type=FieldType.TEXT,
                    value=field.value,
                )
            )
    return fields


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
    node receives the services as an argument). Applies the whole approved
    proposal: entities first (building the ref → real id map), then the
    relationship operations against it (agent/relationships.py). All-or-
    nothing per proposal: a mid-batch failure rolls back the entities created
    so far, so a retry can't duplicate them.

    A proposal may be entities only, relationship operations only, or both —
    "connect these two characters" commits with no entity written at all.

    Acknowledgements are deterministic events (see agent/events.py) — zero
    extra LLM tokens, and language-agnostic: the UI translates the code, the
    English text is only for the model's own conversation history."""
    if state.draft_committed:
        return {}

    # ── Entity-edit path ──────────────────────────────────────────────────────
    if state.entity_edit_draft is not None:
        return await _commit_edit(state, entity_service=entity_service)

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

    ref_to_id: dict[str, str] = {}
    title_to_id = await _build_title_to_id(entity_service, state.project_id)
    titles: list[str] = []
    try:
        for draft_entity in state.draft.entities:
            fields = _build_fields(draft_entity, title_to_id)
            entity = await entity_service.create(
                EntityCreate(
                    type=draft_entity.type, title=draft_entity.title, fields=fields
                ),
                state.project_id,
            )
            ref_to_id[draft_entity.ref] = entity.id
            title_to_id[draft_entity.title.lower()] = entity.id
            titles.append(draft_entity.title)

        ops = await apply_relationship_ops(
            state.draft.relationships,
            edge_service=edge_service,
            project_id=state.project_id,
            ref_to_id=ref_to_id,
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

    # A proposal that only rewires the graph gets its own acknowledgement:
    # "Committed 0 entities" reads like a failure when nothing was meant to
    # be created in the first place.
    if titles:
        message = event_message(
            f"Committed {len(titles)} entities ({', '.join(titles)}) "
            f"and {ops.total} relationships.",
            "batch_committed",
            count=str(len(titles)),
            titles=", ".join(titles),
            edges=str(ops.total),
        )
    else:
        message = event_message(
            f"Committed {ops.created} new relationships, "
            f"{ops.updated} changed, {ops.deleted} removed.",
            "relationships_committed",
            created=str(ops.created),
            updated=str(ops.updated),
            removed=str(ops.deleted),
        )

    return {
        "messages": [message],
        "committed_entity_ids": [*state.committed_entity_ids, *ref_to_id.values()],
        "draft_committed": True,
        # Clear the proposal: smaller checkpoints, and the next propose_lore
        # starts clean. The review snapshot lives in the session registry.
        "draft": None,
        "warnings": ops.warnings,
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
    title_to_id = await _build_title_to_id(entity_service, state.project_id)
    fields = _build_fields(ed, title_to_id)
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
