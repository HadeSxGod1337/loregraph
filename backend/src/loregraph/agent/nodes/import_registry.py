import asyncio
import logging
from typing import Any

from loregraph.agent.import_state import ImportState, WindowSpec
from loregraph.exceptions import GenerationError
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import render
from loregraph.schemas.import_job import RegistryEntry, WindowRegistryDraft
from loregraph.services.event_bus import EVENT_JOB_PROGRESS, EventBus
from loregraph.services.text_similarity import title_similarity
from loregraph.storage.protocols import EntityStore

logger = logging.getLogger(__name__)

NODE = "import_build_registry"

# Real concurrency for the parallel per-window calls below (asyncio.
# TaskGroup, not LangGraph's Send — see agent/import_graph.py's module
# docstring for why), bounded so a big document doesn't fire dozens of
# simultaneous Anthropic calls at once.
MAX_CONCURRENT_LLM_CALLS = 5
# Two names/aliases at or above this fuzzy ratio are treated as the same
# entity — same threshold as check_duplicates.py's DUPLICATE_TITLE_RATIO,
# reused here for the same reason (consistent judgment of "is this a dupe").
FUZZY_MERGE_RATIO = 0.85


def _publish_progress(
    event_bus: EventBus | None,
    project_id: str,
    job_id: str,
    *,
    phase: str,
    done: int,
    total: int,
) -> None:
    if event_bus is not None and job_id:
        event_bus.publish(
            project_id,
            EVENT_JOB_PROGRESS,
            job_id=job_id,
            phase=phase,
            done=done,
            total=total,
        )


async def _build_one_window_registry(
    window: WindowSpec,
    *,
    extraction: StructuredGenerator,
    semaphore: asyncio.Semaphore,
) -> WindowRegistryDraft:
    async with semaphore:
        try:
            result = await extraction.generate(
                WindowRegistryDraft,
                system=render("import_registry.system.md"),
                user=render("import_registry.user.md", document_section=window.text),
            )
            return result.value
        except GenerationError:
            # One window's registry pass failing must not sink the whole
            # job — it just means this window's names get canonicalized at
            # extraction time on a fuzzy-match basis instead of up front.
            logger.warning(
                "Registry pass failed for import window %d; continuing without it",
                window.index,
                exc_info=True,
            )
            return WindowRegistryDraft(entries=[])


def _merge_registry_entries(
    drafts: list[WindowRegistryDraft],
) -> list[RegistryEntry]:
    merged: list[RegistryEntry] = []
    for draft in drafts:
        for entry in draft.entries:
            candidates = [entry.canonical_name.casefold()] + [
                a.casefold() for a in entry.aliases
            ]
            target = next(
                (
                    existing
                    for existing in merged
                    if any(
                        title_similarity(candidate, known.casefold())
                        >= FUZZY_MERGE_RATIO
                        for candidate in candidates
                        for known in (existing.canonical_name, *existing.aliases)
                    )
                ),
                None,
            )
            if target is None:
                merged.append(
                    RegistryEntry(
                        canonical_name=entry.canonical_name,
                        aliases=list(dict.fromkeys(entry.aliases)),
                        type=entry.type,
                    )
                )
                continue
            new_aliases = list(target.aliases)
            for name in (entry.canonical_name, *entry.aliases):
                if name != target.canonical_name and name not in new_aliases:
                    new_aliases.append(name)
            target.aliases = new_aliases
    return merged


async def build_registry(
    state: ImportState,
    *,
    extraction: StructuredGenerator,
    entity_store: EntityStore,
    event_bus: EventBus | None = None,
) -> dict[str, Any]:
    """Cheap, parallel first pass: just names/aliases/types per window
    (Haiku, low temperature — classification, not creativity), merged into
    one canonical registry BEFORE the pricier extraction pass reads any of
    it. This is the step that lets two windows referring to the same
    character under different phrasing end up as one entity instead of two
    (see docstring of agent/nodes/import_registry.py's module)."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
    total = len(state.windows)
    tasks = [
        asyncio.ensure_future(
            _build_one_window_registry(
                window, extraction=extraction, semaphore=semaphore
            )
        )
        for window in state.windows
    ]
    drafts: list[WindowRegistryDraft] = []
    for done, task in enumerate(asyncio.as_completed(tasks), start=1):
        drafts.append(await task)
        _publish_progress(
            event_bus,
            state.project_id,
            state.job_id,
            phase="registry",
            done=done,
            total=total,
        )
    registry = _merge_registry_entries(drafts)

    existing_entities = await entity_store.list_entities(state.project_id)
    for reg_entry in registry:
        match = next(
            (
                existing
                for existing in existing_entities
                if title_similarity(
                    reg_entry.canonical_name.casefold(), existing.title.casefold()
                )
                >= FUZZY_MERGE_RATIO
            ),
            None,
        )
        if match is not None:
            reg_entry.existing_entity_id = match.id

    known_types = sorted(
        {entity.type for entity in existing_entities} | {r.type for r in registry}
    )
    return {"registry": registry, "known_entity_types": known_types}
