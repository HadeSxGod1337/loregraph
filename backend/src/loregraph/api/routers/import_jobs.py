import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from loregraph.agent.runner import AgentEvent
from loregraph.api.deps import (
    ConnectionStoreDep,
    ConnectorRegistryDep,
    ImportJobRunnerDep,
    ImportJobStoreDep,
    KnowledgeSourceStoreDep,
    ProjectStoreDep,
)
from loregraph.connectors.protocols import CAPABILITY_INGEST
from loregraph.exceptions import (
    ConnectionNotFoundError,
    ImportJobNotFoundError,
    ImportJobNotIdleError,
    KnowledgeSourceNotReadyError,
    UnsupportedConnectorCapabilityError,
)
from loregraph.schemas.import_job import (
    ImportJobFromConnectionRequest,
    ImportJobOut,
    ImportJobStartRequest,
    ImportReviewDecision,
)
from loregraph.storage.protocols import ImportJobStore

router = APIRouter(tags=["import-jobs"])

# Statuses that mean "already running" — a project may have at most one
# active bulk import at a time (deliberately simple for v1; nothing
# technical prevents more, but a second concurrent job competing for the
# same LLM concurrency budget and reviewing against a moving canon is more
# confusing than useful).
_ACTIVE_STATUSES = frozenset(
    {"planning", "extracting", "awaiting_review", "committing"}
)


async def _require_no_active_job(project_id: str, jobs: ImportJobStore) -> None:
    existing = await jobs.list_for_project(project_id)
    active = next((j for j in existing if j.status in _ACTIVE_STATUSES), None)
    if active is not None:
        raise ImportJobNotIdleError(active.job_id, active.status)


async def _validate_job(
    jobs: ImportJobStore, project_id: str, job_id: str
) -> ImportJobOut:
    job = await jobs.get(job_id)  # raises ImportJobNotFoundError
    if job.project_id != project_id:
        # Same rule as agent sessions/entities: don't confirm existence
        # across projects.
        raise ImportJobNotFoundError(job_id)
    return job


async def _start_guard(
    project_id: str,
    data: ImportJobStartRequest,
    project_store: ProjectStoreDep,
    source_store: KnowledgeSourceStoreDep,
    jobs: ImportJobStoreDep,
) -> None:
    # Same ordering rationale as api/routers/agent.py's guards: this must
    # resolve — and raise — before ImportJobRunnerDep's ConfigurationError
    # (409, no LLM key) does, so an unready source or unknown project 404s/
    # 409s regardless of whether an LLM is configured.
    await project_store.get(project_id)
    source = await source_store.get(data.source_id)
    # Bulk import re-derives text straight from the stored upload bytes
    # (agent/nodes/import_plan.py), independent of the KB's own embedding
    # index — chunk_count == 0 (embeddings disabled) does NOT block it, only
    # status matters: "ready" means ingestion successfully stored/parsed the
    # file at all.
    if source.project_id != project_id or source.status != "ready":
        raise KnowledgeSourceNotReadyError(data.source_id, source.status)
    await _require_no_active_job(project_id, jobs)


async def _migrate_guard(
    project_id: str,
    data: ImportJobFromConnectionRequest,
    project_store: ProjectStoreDep,
    connection_store: ConnectionStoreDep,
    registry: ConnectorRegistryDep,
    jobs: ImportJobStoreDep,
) -> None:
    # Same ordering rationale as _start_guard: these must resolve — and
    # raise — before ImportJobRunnerDep's ConfigurationError (409, no LLM
    # key), so an unknown connection or a connector that can't be ingested
    # 404s/422s regardless of whether an LLM is configured.
    await project_store.get(project_id)
    connection = await connection_store.get(data.connection_id)
    if connection.project_id != project_id:
        # Same rule as elsewhere: wrong project -> 404, don't confirm the id.
        raise ConnectionNotFoundError(data.connection_id)
    descriptor = registry.get(connection.connector_type)
    if CAPABILITY_INGEST not in descriptor.capabilities:
        raise UnsupportedConnectorCapabilityError(connection.connector_type, "ingest")
    await _require_no_active_job(project_id, jobs)


async def _job_guard(project_id: str, job_id: str, jobs: ImportJobStoreDep) -> None:
    await _validate_job(jobs, project_id, job_id)


async def _sse(events: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _sse_response(events: AsyncIterator[AgentEvent]) -> StreamingResponse:
    return StreamingResponse(
        _sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/projects/{project_id}/import-jobs",
    response_model=None,
)
async def start_import_job(
    project_id: str,
    data: ImportJobStartRequest,
    _guard: Annotated[None, Depends(_start_guard)],
    source_store: KnowledgeSourceStoreDep,
    jobs: ImportJobStoreDep,
    runner: ImportJobRunnerDep,
) -> StreamingResponse:
    """Bulk-import a knowledge-base document into the world graph (see
    agent/import_graph.py). Streamed as SSE: status events per graph phase
    plus job.progress events on the project's WebSocket channel (see
    services/event_bus.py) as individual windows finish, then a review
    event for the first page."""
    source = await source_store.get(data.source_id)
    job_id = uuid.uuid4().hex
    await jobs.create(project_id, job_id, source.id, source.original_filename)
    return _sse_response(
        runner.stream_start(project_id, job_id, source.id, source.original_filename)
    )


@router.post(
    "/projects/{project_id}/import-jobs/from-connection",
    response_model=None,
)
async def start_migration_job(
    project_id: str,
    data: ImportJobFromConnectionRequest,
    _guard: Annotated[None, Depends(_migrate_guard)],
    connection_store: ConnectionStoreDep,
    jobs: ImportJobStoreDep,
    runner: ImportJobRunnerDep,
) -> StreamingResponse:
    """Migrate a connected external tool's OWN content into the world graph
    with AI (see connectors/protocols.py's IngestSource): the connector
    yields its journals/notes as text and the SAME bulk pipeline
    (agent/import_graph.py) extracts entities and relationships, page-by-page
    reviewed before anything reaches canon.

    Distinct from the connection's deterministic Import action, which is a
    round-trip of Loregraph's own export format. This one is for a project
    Loregraph never created."""
    connection = await connection_store.get(data.connection_id)
    job_id = uuid.uuid4().hex
    await jobs.create(project_id, job_id, connection.id, connection.name)
    return _sse_response(
        runner.stream_start(
            project_id,
            job_id,
            connection.id,
            connection.name,
            source_kind="connection",
        )
    )


@router.get(
    "/projects/{project_id}/import-jobs",
    response_model=list[ImportJobOut],
)
async def list_import_jobs(
    project_id: str, jobs: ImportJobStoreDep
) -> list[ImportJobOut]:
    return await jobs.list_for_project(project_id)


@router.get(
    "/projects/{project_id}/import-jobs/{job_id}",
    response_model=ImportJobOut,
)
async def get_import_job(
    project_id: str,
    job_id: str,
    jobs: ImportJobStoreDep,
) -> ImportJobOut:
    return await _validate_job(jobs, project_id, job_id)


@router.post("/projects/{project_id}/import-jobs/{job_id}/review")
async def review_import_job(
    project_id: str,
    job_id: str,
    data: ImportReviewDecision,
    _guard: Annotated[None, Depends(_job_guard)],
    runner: ImportJobRunnerDep,
) -> StreamingResponse:
    """Resolve the current review page — approve (commit + next page),
    reject (skip this page, keep everything already committed), or
    approve_all (commit this AND every remaining page without further
    interrupts — still a real per-page commit_slice write each time, just
    without asking the DM to look at each one; see
    agent/nodes/import_review.py's ImportReviewDecision docstring)."""
    return _sse_response(runner.stream_review(job_id, data))
