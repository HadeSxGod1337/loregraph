import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from loregraph.agent.multimodal import build_message_content
from loregraph.agent.state import AgentState
from loregraph.exceptions import AgentSessionNotFoundError, error_code
from loregraph.observability.protocols import TracingConfig
from loregraph.schemas.agent import (
    AgentMessageOut,
    AgentResumeRequest,
    AgentReviewPayload,
    AgentSessionDetail,
    AgentSessionOut,
    AgentSessionStatus,
    ChatAttachment,
)
from loregraph.storage.protocols import AgentSessionStore

logger = logging.getLogger(__name__)

# Hard wall-clock ceiling per graph turn: a hung LLM call must not leave a
# checkpoint dangling in "running" forever.
AGENT_RUN_TIMEOUT_SECONDS = 600

SESSION_TITLE_LIMIT = 120

type AgentEvent = dict[str, Any]


def _message_text(message: BaseMessage) -> str:
    """Plain text of a message; Anthropic content may be a list of blocks."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def transcript(state: AgentState) -> list[AgentMessageOut]:
    """User-visible conversation: tool plumbing and empty turns filtered out."""
    out: list[AgentMessageOut] = []
    for message in state.messages:
        if isinstance(message, HumanMessage):
            out.append(
                AgentMessageOut(
                    role="user",
                    # Prefer the round-tripped original text over
                    # _message_text: when there are attachments, the message
                    # content also carries an inlined <attached_file> text
                    # block for the model, which _message_text would
                    # otherwise concatenate into what the DM sees.
                    text=message.additional_kwargs.get(
                        "user_text", _message_text(message)
                    ),
                    # Filenames only — never the file bytes — round-tripped
                    # through additional_kwargs (see agent/multimodal.py's
                    # module docstring for why this doesn't touch the
                    # provider-facing content blocks).
                    attachments=list(
                        message.additional_kwargs.get("attachment_filenames", [])
                    ),
                )
            )
        elif isinstance(message, AIMessage):
            text = _message_text(message)
            if text.strip():
                # Deterministic, backend-composed messages (see
                # agent/events.py) carry an event marker the UI prefers over
                # the literal English `text` for rendering.
                event = message.additional_kwargs.get("event")
                out.append(
                    AgentMessageOut(
                        role="assistant",
                        text=text,
                        event_code=event.get("code") if event else None,
                        event_params=event.get("params", {}) if event else {},
                    )
                )
    return out


class AgentRunner:
    """Drives conversation turns across the graph and streams progress events
    (`status` per node, `token` for assistant text, `review` at the HITL
    interrupt, `done` with the updated session) while keeping the session
    registry — the UI's catalog — in sync."""

    def __init__(
        self,
        graph: CompiledStateGraph[AgentState],
        sessions: AgentSessionStore,
        tracing_config: TracingConfig | None = None,
    ) -> None:
        self._graph = graph
        self._sessions = sessions
        self._tracing_config = tracing_config

    async def stream_message(
        self,
        project_id: str,
        thread_id: str,
        text: str,
        anchor_entity_id: str | None,
        attachments: list[ChatAttachment],
    ) -> AsyncIterator[AgentEvent]:
        session = await self._require(project_id, thread_id)
        if session.status == "awaiting_review":
            # A plain dict input on an interrupted thread would just re-fire
            # the interrupt and swallow the message — refuse loudly instead.
            # Defense in depth: the router's _message_guard dependency
            # already blocks this before the stream even opens; this only
            # fires on a race between that check and this one.
            yield {
                "type": "error",
                "code": "awaiting_review_conflict",
                "detail": "A draft is awaiting review — approve, reject or "
                "request changes before sending new messages.",
            }
            return
        if not session.title:
            await self._sessions.update(thread_id, title=text[:SESSION_TITLE_LIMIT])
        message = HumanMessage(
            build_message_content(text, attachments),
            additional_kwargs=(
                {
                    "attachment_filenames": [a.filename for a in attachments],
                    # Text-like attachments are inlined into the message
                    # content as their own {"type": "text"} block (see
                    # agent/multimodal.py) so the model reads them — but that
                    # means _message_text(message) would concatenate the
                    # user's own text with the raw file dump. Round-tripping
                    # what the user actually typed separately keeps the
                    # transcript showing just that, with the file as a chip.
                    "user_text": text,
                }
                if attachments
                else {}
            ),
        )
        graph_input: dict[str, Any] = {
            "project_id": project_id,
            "thread_id": thread_id,
            "anchor_entity_id": anchor_entity_id,
            "messages": [message],
            # Per-turn outcome fields reset so _finalize reports THIS turn's
            # result, not a stale committed/rejected from an earlier proposal.
            "decision_action": None,
            "draft_committed": False,
        }
        async for event in self._stream_turn(thread_id, graph_input, project_id):
            yield event

    async def stream_review(
        self, project_id: str, thread_id: str, decision: AgentResumeRequest
    ) -> AsyncIterator[AgentEvent]:
        session = await self._require(project_id, thread_id)
        if session.status != "awaiting_review":
            # Defense in depth: the router's _review_guard dependency already
            # blocks this; see the matching comment in stream_message.
            yield {
                "type": "error",
                "code": "not_awaiting_review",
                "detail": "Session is not awaiting review.",
            }
            return
        command: Command[Any] = Command(resume=decision.model_dump(mode="json"))
        async for event in self._stream_turn(thread_id, command, project_id):
            yield event

    async def get_detail(self, project_id: str, thread_id: str) -> AgentSessionDetail:
        session = await self._require(project_id, thread_id)
        state = await self._state(thread_id)
        return AgentSessionDetail(
            **session.model_dump(), messages=transcript(state) if state else []
        )

    # -- internals ---------------------------------------------------------

    async def _stream_turn(
        self,
        thread_id: str,
        graph_input: dict[str, Any] | Command[Any],
        project_id: str = "",
    ) -> AsyncIterator[AgentEvent]:
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        if self._tracing_config is not None and project_id:
            meta = self._tracing_config.get_run_metadata(
                project_id=project_id,
                thread_id=thread_id,
                run_name=f"agent_turn:{thread_id[:8]}",
            )
            config["run_name"] = meta.run_name
            config["metadata"] = {
                "project_id": meta.project_id,
                "thread_id": meta.thread_id,
                "tracing_provider": meta.provider,
            }
        await self._sessions.update(thread_id, status="running")
        try:
            async with asyncio.timeout(AGENT_RUN_TIMEOUT_SECONDS):
                async for item in self._graph.astream(
                    graph_input,  # type: ignore[arg-type]
                    config,
                    stream_mode=["updates", "messages"],
                ):
                    # Multi-mode astream yields (mode, payload) tuples.
                    mode, payload = cast(tuple[str, Any], item)
                    if mode == "updates" and isinstance(payload, dict):
                        for node_name in payload:
                            if node_name != "__interrupt__":
                                yield {"type": "status", "node": node_name}
                    elif mode == "messages":
                        message_chunk, metadata = cast(
                            tuple[Any, dict[str, Any]], payload
                        )
                        # Token-stream only the conversational reply; a draft's
                        # structured JSON is unreadable as a token stream.
                        if metadata.get("langgraph_node") == "assistant" and isinstance(
                            message_chunk, BaseMessage
                        ):
                            token = _message_text(message_chunk)
                            if token:
                                yield {"type": "token", "text": token}
        except asyncio.CancelledError:
            await self._sessions.update(thread_id, status="failed")
            raise
        except TimeoutError:
            await self._sessions.update(thread_id, status="failed")
            yield {
                "type": "error",
                "code": "timeout",
                "detail": f"Agent run timed out after {AGENT_RUN_TIMEOUT_SECONDS}s",
            }
            return
        except Exception as exc:
            await self._sessions.update(thread_id, status="failed")
            logger.error("Agent turn failed", exc_info=True)
            yield {"type": "error", "code": error_code(exc), "detail": str(exc)}
            return

        session = await self._finalize(thread_id)
        if session.status == "awaiting_review" and session.review is not None:
            yield {"type": "review", "payload": session.review.model_dump(mode="json")}
        yield {"type": "done", "session": session.model_dump(mode="json")}

    async def _finalize(self, thread_id: str) -> AgentSessionOut:
        """Reconcile the registry with the graph state after a turn."""
        state = await self._state(thread_id)
        if state is None:
            return await self._sessions.update(thread_id, status="failed")
        interrupted = await self._is_interrupted(thread_id)
        if interrupted:
            return await self._sessions.update(
                thread_id,
                status="awaiting_review",
                input_tokens=state.input_tokens,
                output_tokens=state.output_tokens,
                review=AgentReviewPayload(
                    draft=state.draft,
                    entity_edit_draft=state.entity_edit_draft,
                    warnings=state.warnings,
                    input_tokens=state.input_tokens,
                    output_tokens=state.output_tokens,
                ),
            )
        if state.draft_committed:
            status: AgentSessionStatus = "committed"
        elif state.decision_action == "reject":
            status = "rejected"
        else:
            status = "idle"
        return await self._sessions.update(
            thread_id,
            status=status,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            committed_entity_ids=state.committed_entity_ids,
            # The pending-review snapshot is resolved — clear it so a
            # committed/rejected session can't resurrect a stale draft.
            clear_review=True,
        )

    async def _state(self, thread_id: str) -> AgentState | None:
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        snapshot = await self._graph.aget_state(config)
        if not snapshot.values:
            return None
        values = snapshot.values
        if isinstance(values, AgentState):
            return values
        return AgentState.model_validate(values)

    async def _is_interrupted(self, thread_id: str) -> bool:
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        snapshot = await self._graph.aget_state(config)
        return bool(snapshot.next) and any(task.interrupts for task in snapshot.tasks)

    async def _require(self, project_id: str, thread_id: str) -> AgentSessionOut:
        session = await self._sessions.get(thread_id)
        if session.project_id != project_id:
            # Same rule as entities: don't confirm existence across projects.
            raise AgentSessionNotFoundError(thread_id)
        return session
