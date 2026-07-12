import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from loregraph.agent.runner import AgentEvent
from loregraph.api.deps import (
    AgentRunnerDep,
    AgentSessionStoreDep,
    ProjectStoreDep,
    SettingsDep,
    VectorIndexDep,
)
from loregraph.exceptions import AgentSessionNotFoundError, CampaignError
from loregraph.llm.factory import is_llm_configured
from loregraph.schemas.agent import (
    AgentConfigOut,
    AgentMessageRequest,
    AgentResumeRequest,
    AgentSessionDetail,
    AgentSessionOut,
    AgentSessionStatus,
)
from loregraph.storage.protocols import AgentSessionStore

router = APIRouter(tags=["agent"])


# Session checks are DEPENDENCIES declared before AgentRunnerDep in the
# endpoint signatures, for two reasons: (1) they must run before the
# ConfigurationError (409) that building the runner raises when no LLM key is
# set — an unknown session is a 404 regardless of configuration; (2) they must
# happen before the StreamingResponse is returned, because once SSE headers
# (200) are committed an exception inside the generator can only abort the
# stream, never become a clean 404/400.


async def _validate_session(
    sessions: AgentSessionStore,
    project_id: str,
    thread_id: str,
    required_status: AgentSessionStatus | None = None,
    forbidden_status: AgentSessionStatus | None = None,
) -> None:
    session = await sessions.get(thread_id)  # raises AgentSessionNotFoundError
    if session.project_id != project_id:
        # Same rule as entities: don't confirm existence across projects.
        raise AgentSessionNotFoundError(thread_id)
    if required_status is not None and session.status != required_status:
        raise CampaignError(
            f"Session is not awaiting review (status: {session.status})."
        )
    if forbidden_status is not None and session.status == forbidden_status:
        raise CampaignError(
            "A draft is awaiting review — approve, reject or request changes "
            "before sending new messages."
        )


async def _session_exists_guard(
    project_id: str, thread_id: str, sessions: AgentSessionStoreDep
) -> None:
    await _validate_session(sessions, project_id, thread_id)


async def _message_guard(
    project_id: str, thread_id: str, sessions: AgentSessionStoreDep
) -> None:
    await _validate_session(
        sessions, project_id, thread_id, forbidden_status="awaiting_review"
    )


async def _review_guard(
    project_id: str, thread_id: str, sessions: AgentSessionStoreDep
) -> None:
    await _validate_session(
        sessions, project_id, thread_id, required_status="awaiting_review"
    )


async def _sse(events: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _sse_response(events: AsyncIterator[AgentEvent]) -> StreamingResponse:
    return StreamingResponse(
        _sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/agent/config", response_model=AgentConfigOut)
async def agent_config(
    settings: SettingsDep, vector_index: VectorIndexDep
) -> AgentConfigOut:
    """Onboarding probe for the UI — never raises over missing keys."""
    return AgentConfigOut(
        llm_configured=is_llm_configured(settings),
        llm_provider=settings.llm_provider,
        vector_enabled=vector_index is not None,
    )


@router.post(
    "/projects/{project_id}/agent/sessions",
    response_model=AgentSessionOut,
    status_code=201,
)
async def create_agent_session(
    project_id: str,
    sessions: AgentSessionStoreDep,
    project_store: ProjectStoreDep,
) -> AgentSessionOut:
    """Registry-only: creating a conversation needs no LLM configured."""
    await project_store.get(project_id)  # 404 for unknown projects
    return await sessions.create(project_id, uuid.uuid4().hex)


@router.get(
    "/projects/{project_id}/agent/sessions",
    response_model=list[AgentSessionOut],
)
async def list_agent_sessions(
    project_id: str, sessions: AgentSessionStoreDep
) -> list[AgentSessionOut]:
    return await sessions.list_for_project(project_id)


@router.get(
    "/projects/{project_id}/agent/sessions/{thread_id}",
    response_model=AgentSessionDetail,
)
async def get_agent_session(
    project_id: str,
    thread_id: str,
    _guard: Annotated[None, Depends(_session_exists_guard)],
    runner: AgentRunnerDep,
) -> AgentSessionDetail:
    return await runner.get_detail(project_id, thread_id)


@router.post("/projects/{project_id}/agent/sessions/{thread_id}/messages")
async def send_agent_message(
    project_id: str,
    thread_id: str,
    data: AgentMessageRequest,
    _guard: Annotated[None, Depends(_message_guard)],
    runner: AgentRunnerDep,
) -> StreamingResponse:
    """One conversation turn, streamed as SSE: status/token/review/done."""
    return _sse_response(
        runner.stream_message(project_id, thread_id, data.text, data.anchor_entity_id)
    )


@router.post("/projects/{project_id}/agent/sessions/{thread_id}/review")
async def review_agent_session(
    project_id: str,
    thread_id: str,
    data: AgentResumeRequest,
    _guard: Annotated[None, Depends(_review_guard)],
    runner: AgentRunnerDep,
) -> StreamingResponse:
    """Resolve a pending review (approve/reject/revise), streamed as SSE —
    revise streams the regeneration and ends in a fresh review event."""
    return _sse_response(runner.stream_review(project_id, thread_id, data))
