import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from loregraph.agent.import_state import ImportState
from loregraph.agent.nodes.import_review import build_review_payload
from loregraph.agent.runner import AgentEvent
from loregraph.exceptions import error_code
from loregraph.schemas.import_job import (
    ImportJobOut,
    ImportJobStatus,
    ImportReviewDecision,
)
from loregraph.storage.protocols import ImportJobStore

logger = logging.getLogger(__name__)

# Bulk imports can legitimately run much longer than a single chat turn
# (dozens of parallel LLM calls across a whole document) — a generous
# ceiling, not the chat graph's 600s, so a real document doesn't get cut off
# mid-extraction. Still hard, for the same reason AgentRunner has one: a
# hung call must not leave a job stuck in "extracting" forever.
IMPORT_RUN_TIMEOUT_SECONDS = 1800


class ImportJobRunner:
    """Drives a bulk-import job across turns (start, then one resume per
    review page) exactly like AgentRunner drives chat turns — same SSE
    event shapes (status/review/done/error), same checkpointer-backed
    resumability, same registry-table split (ImportJobStore is to
    ImportState what AgentSessionStore is to AgentState)."""

    def __init__(
        self, graph: CompiledStateGraph[ImportState], jobs: ImportJobStore
    ) -> None:
        self._graph = graph
        self._jobs = jobs

    async def stream_start(
        self, project_id: str, job_id: str, source_id: str, source_filename: str
    ) -> AsyncIterator[AgentEvent]:
        graph_input: dict[str, Any] = {
            "project_id": project_id,
            "job_id": job_id,
            "source_id": source_id,
            "source_filename": source_filename,
        }
        async for event in self._stream_turn(job_id, graph_input):
            yield event

    async def stream_review(
        self, job_id: str, decision: ImportReviewDecision
    ) -> AsyncIterator[AgentEvent]:
        job = await self._jobs.get(job_id)
        if job.status != "awaiting_review":
            # Defense in depth: the router's guard already blocks this.
            yield {
                "type": "error",
                "code": "not_awaiting_review",
                "detail": "Import job is not awaiting review.",
            }
            return
        command: Command[Any] = Command(resume=decision.model_dump(mode="json"))
        async for event in self._stream_turn(job_id, command):
            yield event

    async def get_detail(self, job_id: str) -> ImportJobOut:
        return await self._jobs.get(job_id)

    # -- internals ---------------------------------------------------------

    async def _stream_turn(
        self, job_id: str, graph_input: dict[str, Any] | Command[Any]
    ) -> AsyncIterator[AgentEvent]:
        config: RunnableConfig = {"configurable": {"thread_id": job_id}}
        await self._jobs.update(job_id, status="extracting")
        try:
            async with asyncio.timeout(IMPORT_RUN_TIMEOUT_SECONDS):
                async for update in self._graph.astream(
                    graph_input,  # type: ignore[arg-type]
                    config,
                    stream_mode="updates",
                ):
                    if isinstance(update, dict):
                        for node_name in update:
                            if node_name != "__interrupt__":
                                yield {"type": "status", "node": node_name}
        except asyncio.CancelledError:
            await self._jobs.update(job_id, status="failed")
            raise
        except TimeoutError:
            await self._jobs.update(job_id, status="failed")
            yield {
                "type": "error",
                "code": "timeout",
                "detail": f"Import job timed out after {IMPORT_RUN_TIMEOUT_SECONDS}s",
            }
            return
        except Exception as exc:
            await self._jobs.update(job_id, status="failed")
            logger.error("Import job failed", exc_info=True)
            yield {"type": "error", "code": error_code(exc), "detail": str(exc)}
            return

        job = await self._finalize(job_id)
        if job.status == "awaiting_review" and job.review is not None:
            yield {"type": "review", "payload": job.review.model_dump(mode="json")}
        yield {"type": "done", "job": job.model_dump(mode="json")}

    async def _finalize(self, job_id: str) -> ImportJobOut:
        state = await self._state(job_id)
        if state is None:
            return await self._jobs.update(job_id, status="failed")
        interrupted = await self._is_interrupted(job_id)
        total_slices = len(state.review_slices)
        if interrupted:
            return await self._jobs.update(
                job_id,
                status="awaiting_review",
                total_windows=len(state.windows),
                total_slices=total_slices,
                current_slice=state.current_slice,
                input_tokens=state.input_tokens,
                output_tokens=state.output_tokens,
                committed_entity_ids=state.committed_entity_ids,
                review=build_review_payload(state) if total_slices else None,
            )
        status: ImportJobStatus = "committed"
        return await self._jobs.update(
            job_id,
            status=status,
            total_windows=len(state.windows),
            total_slices=total_slices,
            current_slice=state.current_slice,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            committed_entity_ids=state.committed_entity_ids,
            clear_review=True,
        )

    async def _state(self, job_id: str) -> ImportState | None:
        config: RunnableConfig = {"configurable": {"thread_id": job_id}}
        snapshot = await self._graph.aget_state(config)
        if not snapshot.values:
            return None
        values = snapshot.values
        if isinstance(values, ImportState):
            return values
        return ImportState.model_validate(cast(dict[str, Any], values))

    async def _is_interrupted(self, job_id: str) -> bool:
        config: RunnableConfig = {"configurable": {"thread_id": job_id}}
        snapshot = await self._graph.aget_state(config)
        return bool(snapshot.next) and any(task.interrupts for task in snapshot.tasks)
