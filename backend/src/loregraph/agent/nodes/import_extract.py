import asyncio
import logging
from typing import Any

from loregraph.agent.import_state import ImportState, WindowExtraction, WindowSpec
from loregraph.exceptions import GenerationError
from loregraph.llm.structured import StructuredGenerator
from loregraph.prompts import render
from loregraph.schemas.agent import LoreDraft
from loregraph.schemas.import_job import RegistryEntry
from loregraph.services.event_bus import EVENT_JOB_PROGRESS, EventBus

logger = logging.getLogger(__name__)

NODE = "import_extract_windows"

MAX_CONCURRENT_LLM_CALLS = 5
# Soft, technical ceiling on ONE window's extraction call — protects a
# single structured-output call from unbounded size/latency/quality
# degradation. NOT a limit on the document: with N windows the total across
# the whole import is unbounded (see prompts/import_extract.system.md
# rule 7). Contrast with generate_lore.system.md's "never exceed 12", which
# IS a real ceiling on one ad-hoc chat proposal.
IMPORT_MAX_ENTITIES_PER_WINDOW = 30


def _registry_block(registry: list[RegistryEntry]) -> str:
    if not registry:
        return "(no names identified yet — extract only what this section itself names)"
    lines = []
    for entry in registry:
        aliases = ", ".join(entry.aliases) if entry.aliases else "—"
        lines.append(f"{entry.canonical_name} (aliases: {aliases}) [{entry.type}]")
    return "\n".join(lines)


async def _extract_one_window(
    window: WindowSpec,
    *,
    creative: StructuredGenerator,
    semaphore: asyncio.Semaphore,
    registry_block: str,
    known_types: str,
) -> WindowExtraction:
    async with semaphore:
        try:
            result = await creative.generate(
                LoreDraft,
                system=render(
                    "import_extract.system.md",
                    max_entities=str(IMPORT_MAX_ENTITIES_PER_WINDOW),
                ),
                user=render(
                    "import_extract.user.md",
                    registry_block=registry_block,
                    known_types=known_types,
                    document_section=window.text,
                ),
            )
            return WindowExtraction(
                index=window.index,
                draft=result.value,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
            )
        except GenerationError:
            # Same tolerance as the registry pass: one window failing
            # validation after retries must not sink the whole import —
            # its content is simply missing from the result, not the
            # entire document's.
            logger.warning(
                "Extraction failed for import window %d; skipping it",
                window.index,
                exc_info=True,
            )
            return WindowExtraction(index=window.index, draft=LoreDraft(entities=[]))


async def extract_windows(
    state: ImportState,
    *,
    creative: StructuredGenerator,
    event_bus: EventBus | None = None,
) -> dict[str, Any]:
    """Parallel, per-window extraction (Sonnet, low-ish temperature — this
    is faithful extraction from source text, not free creative generation,
    unlike generate_lore.py's propose_lore path). Real concurrency via
    asyncio + a semaphore, not LangGraph's Send: every window's call is
    independent and non-interrupting, so a plain gather is simpler and
    avoids Send's less-obvious per-branch state-payload semantics for a
    Pydantic-typed graph state (see agent/import_graph.py)."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
    registry_block = _registry_block(state.registry)
    known_types = ", ".join(state.known_entity_types) or "(none yet)"
    total = len(state.windows)
    tasks = [
        asyncio.ensure_future(
            _extract_one_window(
                window,
                creative=creative,
                semaphore=semaphore,
                registry_block=registry_block,
                known_types=known_types,
            )
        )
        for window in state.windows
    ]
    extractions: list[WindowExtraction] = []
    for done, task in enumerate(asyncio.as_completed(tasks), start=1):
        extractions.append(await task)
        if event_bus is not None and state.job_id:
            event_bus.publish(
                state.project_id,
                EVENT_JOB_PROGRESS,
                job_id=state.job_id,
                phase="extract",
                done=done,
                total=total,
            )
    ordered = sorted(extractions, key=lambda e: e.index)
    total_input = sum(e.input_tokens for e in ordered)
    total_output = sum(e.output_tokens for e in ordered)
    return {
        "extractions": ordered,
        "input_tokens": state.input_tokens + total_input,
        "output_tokens": state.output_tokens + total_output,
    }
