"""In-process pub/sub for project-scoped realtime events.

Local self-hosted tool, single process — no Redis/broker. Kept behind a
small class (not a bare dict of queues) so a future out-of-process bus is a
drop-in swap without touching callers (DIP, same rationale as VectorStore/
GraphStore Protocols elsewhere in this app).

Event types are domain events, not transport framing — the same catalog is
meant to be consumed over WebSocket (api/routers/realtime.py) and, during the
SSE→WS migration, mirrored onto the existing SSE endpoints unchanged.
"""

import asyncio
import itertools
import logging
import time
from collections import deque
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Per-project ring buffer size for reconnect catch-up — bounded so a
# long-lived project can't grow this without limit; older events are simply
# not replayable (the client falls back to a fresh status snapshot via the
# existing REST GETs).
EVENT_BUFFER_SIZE = 500
# Per-subscriber queue depth: a slow/gone client must never backpressure the
# publisher (an agent turn, a commit) — once full, new events are dropped for
# that subscriber only, not queued indefinitely.
SUBSCRIBER_QUEUE_SIZE = 256

# Chat turn streaming (mirrors the existing SSE `status`/`token`/`done`/
# `error` events emitted by agent/runner.py::AgentRunner._stream_turn).
EVENT_CHAT_STATUS = "chat.status"
EVENT_CHAT_TOKEN = "chat.token"
EVENT_CHAT_DONE = "chat.done"
EVENT_CHAT_ERROR = "chat.error"
# HITL gate (mirrors the existing SSE `review` event and its resolution).
EVENT_REVIEW_REQUESTED = "review.requested"
EVENT_REVIEW_RESOLVED = "review.resolved"
# Long-running background jobs (knowledge ingest, bulk import, future skills).
EVENT_JOB_PHASE = "job.phase"
EVENT_JOB_PROGRESS = "job.progress"
EVENT_JOB_DONE = "job.done"
EVENT_JOB_FAILED = "job.failed"
# Knowledge base document ingestion status (replaces frontend polling).
EVENT_KNOWLEDGE_INGEST_STATUS = "knowledge.ingest_status"
# World graph writes — lets an open graph view update live as an agent/job
# commits, instead of only refreshing on next manual navigation.
EVENT_WORLD_ENTITY_COMMITTED = "world.entity_committed"
EVENT_WORLD_EDGE_COMMITTED = "world.edge_committed"


class Event(BaseModel):
    seq: int
    type: str
    project_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: float


class _ProjectChannel:
    """Ring buffer + fan-out for one project's events."""

    def __init__(self, buffer_size: int) -> None:
        self._buffer: deque[Event] = deque(maxlen=buffer_size)
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._seq = itertools.count(1)

    def publish(self, project_id: str, type_: str, payload: dict[str, Any]) -> Event:
        event = Event(
            seq=next(self._seq),
            type=type_,
            project_id=project_id,
            payload=payload,
            ts=time.time(),
        )
        self._buffer.append(event)
        # Best-effort fan-out: a subscriber whose queue is full gets the
        # event dropped rather than backpressuring the publisher — a slow
        # WebSocket client must never stall an agent turn or a commit.
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Event subscriber queue full for project %s (type=%s) — "
                    "dropping for this subscriber; it will miss this event.",
                    project_id,
                    type_,
                )
        return event

    def catch_up(self, from_seq: int) -> list[Event]:
        return [e for e in self._buffer if e.seq > from_seq]

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)


class EventBus:
    """Project-scoped pub/sub. One channel is created lazily per project_id
    and lives for the process lifetime (cheap: a deque + a set of queues)."""

    def __init__(self, buffer_size: int = EVENT_BUFFER_SIZE) -> None:
        self._buffer_size = buffer_size
        self._channels: dict[str, _ProjectChannel] = {}

    def _channel(self, project_id: str) -> _ProjectChannel:
        channel = self._channels.get(project_id)
        if channel is None:
            channel = _ProjectChannel(self._buffer_size)
            self._channels[project_id] = channel
        return channel

    def publish(self, project_id: str, type_: str, **payload: Any) -> Event:
        return self._channel(project_id).publish(project_id, type_, payload)

    async def subscribe(
        self, project_id: str, *, catch_up_from: int | None = None
    ) -> AsyncGenerator[Event, None]:
        """Yields buffered events newer than `catch_up_from` (if given), then
        streams live events until the consumer stops iterating (or the task
        is cancelled — e.g. the WebSocket disconnects)."""
        channel = self._channel(project_id)
        if catch_up_from is not None:
            for event in channel.catch_up(catch_up_from):
                yield event
        queue = channel.subscribe()
        try:
            while True:
                yield await queue.get()
        finally:
            channel.unsubscribe(queue)
