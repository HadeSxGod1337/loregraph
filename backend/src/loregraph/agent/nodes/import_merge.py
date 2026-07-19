from typing import Any

from loregraph.agent.import_state import ImportState
from loregraph.schemas.agent import AgentWarning, DraftEntity
from loregraph.services.text_similarity import title_similarity
from loregraph.storage.protocols import EntityStore

NODE = "import_merge_extractions"

# Same threshold as import_registry.py's registry merge and the main chat
# pipeline's check_duplicates.py — one consistent notion of "same entity".
FUZZY_MERGE_RATIO = 0.85


async def merge_extractions(
    state: ImportState, *, entity_store: EntityStore
) -> dict[str, Any]:
    """Runs once, after every window's extraction has completed: resolves
    entities across ALL windows into one deduplicated set (exact/fuzzy title
    match against each other AND against existing project canon), remaps
    every relationship's endpoints through that resolution, and drops
    (with a warning, never silently) any relationship that still can't be
    resolved to something in this merged set or the existing canon.

    Entities are what the DM reviews page by page (agent/nodes/
    import_review.py); relationships are committed in one final pass after
    every page is resolved (agent/nodes/import_commit.py's
    commit_relationships) — a relationship may point at an entity from a
    page that hasn't committed yet, which only that later pass (using
    ImportState.ref_to_id, populated as pages commit) can resolve."""
    existing_entities = await entity_store.list_entities(state.project_id)
    # title/alias (casefold) -> final id/ref. Existing canon populates it
    # first so a fuzzy match against canon always wins over creating a new
    # entity with a similar name.
    title_to_final: dict[str, str] = {
        entity.title.casefold(): entity.id for entity in existing_entities
    }
    existing_ids = {entity.id for entity in existing_entities}
    for reg_entry in state.registry:
        if reg_entry.existing_entity_id is None:
            continue
        for name in (reg_entry.canonical_name, *reg_entry.aliases):
            title_to_final.setdefault(name.casefold(), reg_entry.existing_entity_id)

    kept_entities: list[DraftEntity] = []
    merge_notes: list[AgentWarning] = []
    # "w{window_index}_{local_ref}" -> final ref ("mN") or existing entity id.
    local_ref_to_final: dict[str, str] = {}

    for extraction in state.extractions:
        for entity in extraction.draft.entities:
            local_key = f"w{extraction.index}_{entity.ref}"
            title_cf = entity.title.casefold()
            final = title_to_final.get(title_cf)
            if final is None:
                final = next(
                    (
                        known_final
                        for known_title, known_final in title_to_final.items()
                        if title_similarity(title_cf, known_title) >= FUZZY_MERGE_RATIO
                    ),
                    None,
                )
            if final is not None:
                local_ref_to_final[local_key] = final
                code = (
                    "import_linked_existing"
                    if final in existing_ids
                    else ("import_merged_duplicate")
                )
                params = (
                    {"title": entity.title, "existing_id": final}
                    if code == "import_linked_existing"
                    else {"title": entity.title}
                )
                merge_notes.append(AgentWarning(code=code, params=params))
                continue
            new_ref = f"m{len(kept_entities)}"
            kept_entities.append(entity.model_copy(update={"ref": new_ref}))
            local_ref_to_final[local_key] = new_ref
            title_to_final[title_cf] = new_ref

    def _resolve(window_index: int, ref_or_name: str) -> str | None:
        local_key = f"w{window_index}_{ref_or_name}"
        if local_key in local_ref_to_final:
            return local_ref_to_final[local_key]
        return title_to_final.get(ref_or_name.casefold())

    kept_relationships = []
    seen_edges: set[tuple[str, str, str]] = set()
    for extraction in state.extractions:
        for relationship in extraction.draft.relationships:
            source = _resolve(extraction.index, relationship.source_ref)
            target = _resolve(extraction.index, relationship.target_ref)
            if source is None or target is None:
                merge_notes.append(
                    AgentWarning(
                        code="import_relationship_unresolved",
                        params={
                            "source": relationship.source_ref,
                            "target": relationship.target_ref,
                        },
                    )
                )
                continue
            edge_key = (source, target, relationship.type)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            kept_relationships.append(
                relationship.model_copy(
                    update={"source_ref": source, "target_ref": target}
                )
            )

    return {
        "merged_entities": kept_entities,
        "merge_notes": merge_notes,
        "pending_relationships": kept_relationships,
    }
