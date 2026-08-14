import asyncio
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage

from loregraph.agent.events import event_message
from loregraph.agent.relationships import RelationshipOpsResult, apply_relationship_ops
from loregraph.agent.state import AgentState
from loregraph.exceptions import EdgeNotFoundError
from loregraph.schemas.agent import (
    AgentWarning,
    DraftEntity,
    DraftEntityPatch,
    EntityEditDraft,
    LoreDraft,
)
from loregraph.schemas.entity import (
    EntityCreate,
    EntityFieldIn,
    EntityPatch,
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


def _field_in(field: Any, title_to_id: dict[str, str]) -> EntityFieldIn:
    """One draft field → one EntityFieldIn, converting a rich_text value that
    carries ``[[label]]`` wikilinks into a ProseMirror doc."""
    if getattr(field, "field_type", FieldType.TEXT) == FieldType.RICH_TEXT:
        return EntityFieldIn(
            key=field.key,
            field_type=FieldType.RICH_TEXT,
            value=_wikilinks_to_prosemirror(field.value, title_to_id),
        )
    return EntityFieldIn(key=field.key, field_type=FieldType.TEXT, value=field.value)


def _build_fields(
    draft_entity: DraftEntity | EntityEditDraft,
    title_to_id: dict[str, str],
) -> list[EntityFieldIn]:
    """Full field list for a newly created entity: summary first, then every
    draft field."""
    return [
        EntityFieldIn(
            key="summary",
            field_type=FieldType.TEXT,
            value=draft_entity.summary,
            show_on_card=True,
        ),
        *(_field_in(field, title_to_id) for field in draft_entity.fields),
    ]


def _build_patch(patch: DraftEntityPatch, title_to_id: dict[str, str]) -> EntityPatch:
    """A draft patch → the store-level EntityPatch. Only what the model named
    is carried; removal is explicit (remove_field_keys) and the store keeps
    every untouched field and its flags (storage/sqlite/entity_store.py::
    patch)."""
    return EntityPatch(
        type=patch.type,
        title=patch.title,
        set_fields=[_field_in(field, title_to_id) for field in patch.set_fields],
        remove_field_keys=patch.remove_field_keys,
    )


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


async def _preflight(
    draft: LoreDraft,
    entity_service: EntityService,
    edge_service: EdgeService,
    project_id: str,
) -> list[AgentWarning]:
    """Validate the approved proposal against the CURRENT world, immediately
    before any write — so a review that went stale (an entity deleted, an edge
    removed, or a namesake created since the DM saw the card) is caught and the
    whole proposal is refused cleanly, never applied half-way.

    Returns the problems found; an empty list means it is safe to write. This
    narrows but does not fully close the write window: the stores autocommit
    per operation (there is no cross-service transaction without a storage
    rewrite this task deliberately does not do), so a failure BETWEEN these
    checks and the writes below still cannot roll a completed patch back.
    Preflight makes that window small; commit() reports the remaining limit
    honestly rather than claiming an atomicity it does not have."""
    problems: list[AgentWarning] = []
    existing = await entity_service.list_entities(project_id)
    existing_ids = {entity.id for entity in existing}
    id_by_title = {entity.title.casefold(): entity.id for entity in existing}
    draft_refs = {entity.ref for entity in draft.entities}

    # A patch is an in-place edit with no clean inverse — the one write that
    # cannot be compensated — so a vanished target is the most important thing
    # to catch before writing anything.
    for patch in draft.patches:
        if patch.entity_id not in existing_ids:
            problems.append(
                AgentWarning(code="stale_patch_target", params={"id": patch.entity_id})
            )

    # A created title that now collides with an existing one means a namesake
    # appeared since validation (validation already dropped clones of entities
    # that existed then) — writing it would silently duplicate the world.
    for entity in draft.entities:
        existing_id = id_by_title.get(entity.title.casefold())
        if existing_id is not None:
            problems.append(
                AgentWarning(
                    code="stale_duplicate_title",
                    params={"title": entity.title, "existing_id": existing_id},
                )
            )

    for relationship in draft.relationships:
        if relationship.op in ("update", "delete"):
            edge_id = relationship.edge_id or ""
            try:
                await edge_service.get_in_project(project_id, edge_id)
            except EdgeNotFoundError:
                problems.append(
                    AgentWarning(
                        code="stale_relationship_edge",
                        params={"edge_id": edge_id, "op": relationship.op},
                    )
                )
        else:  # create: existing-entity endpoints must still exist (draft refs
            # are created below, so they are always fine)
            for ref in (relationship.source_ref, relationship.target_ref):
                if ref and ref not in draft_refs and ref not in existing_ids:
                    problems.append(
                        AgentWarning(
                            code="stale_relationship_endpoint", params={"ref": ref}
                        )
                    )
    return problems


REVIEW_STALE_MESSAGE = (
    "Proposal not applied — the world changed since this was reviewed. Nothing "
    "was written; re-run the request against the current world."
)


async def commit(
    state: AgentState,
    *,
    entity_service: EntityService,
    edge_service: EdgeService,
) -> dict[str, Any]:
    """The only node with write access (structural HITL guarantee — no other
    node receives the services as an argument). Applies the whole approved
    proposal: entities first (building the ref → real id map), then patches,
    then the relationship operations against it (agent/relationships.py).

    Not fully atomic, and does not claim to be. A `_preflight` pass runs
    immediately before any write and refuses the whole proposal if the review
    has gone stale, which is what makes a mid-write failure unlikely. If one
    still happens, entities created so far are rolled back (a retry can't
    duplicate them), but a patch already applied to a pre-existing entity has
    no clean inverse and cannot be — the stores autocommit per operation. So
    ordering is create → patch → relationship-ops (destructive edge deletes
    last), and the honest guarantee is "preflighted, creates compensated",
    not all-or-nothing.

    A proposal may be entities only, relationship operations only, or both —
    "connect these two characters" commits with no entity written at all.

    Acknowledgements are deterministic events (see agent/events.py) — zero
    extra LLM tokens, and language-agnostic: the UI translates the code, the
    English text is only for the model's own conversation history."""
    if state.draft_committed:
        return {}

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

    # ── Preflight: refuse a stale review cleanly, before touching anything ────
    problems = await _preflight(
        state.draft, entity_service, edge_service, state.project_id
    )
    if problems:
        logger.warning(
            "Commit refused: review is stale (%d problem(s)); nothing written.",
            len(problems),
        )
        return {
            "messages": [
                event_message(
                    REVIEW_STALE_MESSAGE,
                    "review_stale",
                    problems=str(len(problems)),
                )
            ],
            "draft": None,
            "warnings": problems,
            "pending_brief": "",
        }

    # ── Apply the whole approved proposal, in a safe order ────────────────────
    # create → patch → relationship ops. Creates come first so relationships
    # can reference the new ids; patches edit entities that already existed, so
    # order relative to creates does not matter, but they run before the
    # relationship ops for the same reason the ops run last: deletion (of an
    # edge) is the only step that cannot be compensated (agent/relationships.py).
    ref_to_id: dict[str, str] = {}
    title_to_id = await _build_title_to_id(entity_service, state.project_id)
    titles: list[str] = []
    patched_titles: list[str] = []
    patched_ids: list[str] = []
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

        for patch in state.draft.patches:
            updated = await entity_service.patch(
                state.project_id,
                patch.entity_id,
                _build_patch(patch, title_to_id),
            )
            patched_titles.append(updated.title)
            patched_ids.append(updated.id)

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
        # Only created entities can be compensated — a patch is an in-place
        # edit of pre-existing state with no clean inverse. Rolling back the
        # creates still prevents a retried approve from duplicating them, which
        # is the failure this guard exists to stop.
        await _rollback_created(
            entity_service, state.project_id, list(ref_to_id.values())
        )
        raise

    message = _commit_message(titles, patched_titles, ops)
    return {
        "messages": [message],
        # Both created AND patched entities changed, so both are pushed to
        # connectors and announced as committed (see agent/runner.py).
        "committed_entity_ids": [
            *state.committed_entity_ids,
            *ref_to_id.values(),
            *patched_ids,
        ],
        "draft_committed": True,
        # Clear the proposal: smaller checkpoints, and the next proposal starts
        # clean. The review snapshot lives in the session registry.
        "draft": None,
        "warnings": ops.warnings,
        "pending_brief": "",
    }


def _commit_message(
    created_titles: list[str],
    patched_titles: list[str],
    ops: "RelationshipOpsResult",
) -> AIMessage:
    """One acknowledgement covering everything the proposal did. A relationship-
    only or patch-only proposal reads correctly instead of "Committed 0
    entities", which looked like a failure.

    Titles go into the canonical English text (not just params) so the model's
    own conversation history names what it just changed — the frontend still
    renders the localized version from the params."""
    parts: list[str] = []
    if created_titles:
        parts.append(f"created {', '.join(created_titles)}")
    if patched_titles:
        parts.append(f"edited {', '.join(patched_titles)}")
    if ops.total:
        parts.append(f"{ops.total} relationship ops")
    summary = "; ".join(parts) if parts else "nothing (empty proposal)"
    return event_message(
        f"Committed: {summary}.",
        "changes_committed",
        created=str(len(created_titles)),
        created_titles=", ".join(created_titles),
        patched=str(len(patched_titles)),
        patched_titles=", ".join(patched_titles),
        rel_created=str(ops.created),
        rel_updated=str(ops.updated),
        rel_deleted=str(ops.deleted),
    )
