import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from loregraph.agent.state import AgentState
from loregraph.exceptions import AgentSessionNotFoundError
from loregraph.schemas.agent import (
    AgentMessageOut,
    AgentResumeRequest,
    AgentReviewPayload,
    AgentSessionDetail,
    AgentSessionOut,
    AgentSessionStatus,
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
            out.append(AgentMessageOut(role="user", text=_message_text(message)))
        elif isinstance(message, AIMessage):
            text = _message_text(message)
            if text.strip():
                out.append(AgentMessageOut(role="assistant", text=text))
    return out


class AgentRunner:
    """Drives conversation turns across the graph and streams progress events
    (`status` per node, `token` for assistant text, `review` at the HITL
    interrupt, `done` with the updated session) while keeping the session
    registry — the UI's catalog — in sync."""

    def __init__(
        self, graph: CompiledStateGraph[AgentState], sessions: AgentSessionStore
    ) -> None:
        self._graph = graph
        self._sessions = sessions

    async def stream_message(
        self, project_id: str, thread_id: str, text: str, anchor_entity_id: str | None
    ) -> AsyncIterator[AgentEvent]:
        session = await self._require(project_id, thread_id)
        if not session.title:
            await self._sessions.update(thread_id, title=text[:SESSION_TITLE_LIMIT])
        graph_input: dict[str, Any] = {
            "project_id": project_id,
            "anchor_entity_id": anchor_entity_id,
            "messages": [HumanMessage(text)],
        }
        async for event in self._stream_turn(thread_id, graph_input):
            yield event

    async def stream_review(
        self, project_id: str, thread_id: str, decision: AgentResumeRequest
    ) -> AsyncIterator[AgentEvent]:
        session = await self._require(project_id, thread_id)
        if session.status != "awaiting_review":
            yield {"type": "error", "detail": "Session is not awaiting review."}
            return
        command: Command[Any] = Command(resume=decision.model_dump(mode="json"))
        async for event in self._stream_turn(thread_id, command):
            yield event

    async def get_detail(self, project_id: str, thread_id: str) -> AgentSessionDetail:
        session = await self._require(project_id, thread_id)
        state = await self._state(thread_id)
        return AgentSessionDetail(
            **session.model_dump(), messages=transcript(state) if state else []
        )

    # -- internals ---------------------------------------------------------

    async def _stream_turn(
        self, thread_id: str, graph_input: dict[str, Any] | Command[Any]
    ) -> AsyncIterator[AgentEvent]:
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
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
                "detail": f"Agent run timed out after {AGENT_RUN_TIMEOUT_SECONDS}s",
            }
            return
        except Exception as exc:
            await self._sessions.update(thread_id, status="failed")
            logger.error("Agent turn failed", exc_info=True)
            yield {"type": "error", "detail": str(exc)}
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
                    warnings=state.warnings,
                    input_tokens=state.input_tokens,
                    output_tokens=state.output_tokens,
                ),
            )
        status: AgentSessionStatus = "committed" if state.draft_committed else "idle"
        return await self._sessions.update(
            thread_id,
            status=status,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            committed_entity_ids=state.committed_entity_ids,
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
