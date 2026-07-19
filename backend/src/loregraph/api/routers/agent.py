import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from loregraph.agent.multimodal import build_message_content
from loregraph.agent.runner import AgentEvent
from loregraph.agent.skills.registry import SKILLS
from loregraph.api.deps import (
    AgentRunnerDep,
    AgentSessionStoreDep,
    ProjectStoreDep,
    SettingsDep,
    VectorIndexDep,
)
from loregraph.exceptions import (
    AgentSessionNotFoundError,
    AwaitingReviewConflictError,
    ChatAttachmentLimitExceededError,
    NotAwaitingReviewError,
    SkillInputInvalidError,
    UnknownSkillError,
)
from loregraph.llm.factory import is_llm_configured
from loregraph.schemas.agent import (
    AgentConfigOut,
    AgentMessageRequest,
    AgentResumeRequest,
    AgentSessionDetail,
    AgentSessionOut,
    AgentSessionStatus,
    AgentSkillRunRequest,
    ChatAttachment,
)
from loregraph.storage.protocols import AgentSessionStore

router = APIRouter(tags=["agent"])

# Local self-hosted tool, no upload proxy in front — cap chat attachments here
# so one oversized/over-numerous payload can't blow up the checkpointed
# conversation or a single LLM call's cost.
MAX_CHAT_ATTACHMENT_BYTES = 15 * 1024 * 1024
MAX_CHAT_ATTACHMENTS_PER_TURN = 4


def _validate_attachments(attachments: list[ChatAttachment]) -> None:
    if len(attachments) > MAX_CHAT_ATTACHMENTS_PER_TURN:
        raise ChatAttachmentLimitExceededError(
            f"at most {MAX_CHAT_ATTACHMENTS_PER_TURN} files per message "
            f"(got {len(attachments)})"
        )
    for attachment in attachments:
        # base64 is ~4/3 the size of the decoded bytes — a cheap pre-check
        # that avoids decoding an oversized payload just to reject it.
        approx_bytes = len(attachment.data_base64) * 3 // 4
        if approx_bytes > MAX_CHAT_ATTACHMENT_BYTES:
            raise ChatAttachmentLimitExceededError(
                f"{attachment.filename!r} exceeds the "
                f"{MAX_CHAT_ATTACHMENT_BYTES // (1024 * 1024)}MB per-file limit"
            )
    # Eagerly builds the content blocks to surface UnsupportedAttachmentTypeError
    # as a clean 422 now: stream_message is an async generator, so an
    # exception raised from inside it could only abort an already-started SSE
    # stream (see the guard-ordering note above).
    build_message_content("", attachments)


async def _attachment_guard(data: AgentMessageRequest) -> None:
    # A Depends(), not a plain call inside the endpoint body: like the
    # session guards below, this must run BEFORE AgentRunnerDep's
    # dependency resolution (which raises ConfigurationError/409 with no LLM
    # key configured) — a malformed/oversized attachment is a 422 regardless
    # of whether an LLM is configured, and Depends() parameters all resolve
    # before the endpoint function body runs, so ordering can only be
    # controlled via Depends() placement, not code position in the body.
    _validate_attachments(data.attachments)


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
        raise NotAwaitingReviewError(session.status)
    if forbidden_status is not None and session.status == forbidden_status:
        raise AwaitingReviewConflictError()


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


async def _skill_run_guard(
    project_id: str,
    thread_id: str,
    skill_name: str,
    data: AgentSkillRunRequest,
    sessions: AgentSessionStoreDep,
) -> dict[str, Any]:
    # Same ordering rule as the session guards above: an unknown skill name
    # or malformed input is a 404/422 regardless of whether an LLM key is
    # configured, so this must resolve — and raise — before AgentRunnerDep
    # does. Returns the already-validated input dict for the endpoint to use
    # directly, so the skill's own schema is only parsed once.
    await _validate_session(
        sessions, project_id, thread_id, forbidden_status="awaiting_review"
    )
    manifest = SKILLS.get(skill_name)
    if manifest is None or manifest.entry_node is None:
        # Unknown name, or a "read" skill — those only run inline inside a
        # chat turn's tool-call loop, never as a standalone graph entry.
        raise UnknownSkillError(skill_name)
    try:
        validated = manifest.input_schema.model_validate(data.input)
    except ValidationError as e:
        raise SkillInputInvalidError(skill_name, str(e)) from e
    return validated.model_dump(mode="json")


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
    _attachment_guard_dep: Annotated[None, Depends(_attachment_guard)],
    runner: AgentRunnerDep,
) -> StreamingResponse:
    """One conversation turn, streamed as SSE: status/token/review/done."""
    return _sse_response(
        runner.stream_message(
            project_id,
            thread_id,
            data.text,
            data.anchor_entity_id,
            data.attachments,
        )
    )


@router.post(
    "/projects/{project_id}/agent/sessions/{thread_id}/skills/{skill_name}/run"
)
async def run_agent_skill(
    project_id: str,
    thread_id: str,
    skill_name: str,
    validated_input: Annotated[dict[str, Any], Depends(_skill_run_guard)],
    runner: AgentRunnerDep,
) -> StreamingResponse:
    """Second entry point for a skill (see agent/skills/registry.py): runs
    it directly, with no assistant LLM call deciding whether to fire —
    for UI-driven triggers (a button) that must work deterministically
    regardless of model judgment. Streamed as SSE, same status/review/done
    shape as /messages."""
    return _sse_response(
        runner.stream_skill_run(project_id, thread_id, skill_name, validated_input)
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
