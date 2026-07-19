import asyncio

import pytest

from loregraph.services.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_before_subscribe_is_not_delivered_live() -> None:
    bus = EventBus()
    bus.publish("p1", "job.phase", phase="planning")

    events = []

    async def collect() -> None:
        async for event in bus.subscribe("p1"):
            events.append(event)
            if len(events) == 1:
                return

    task = asyncio.ensure_future(collect())
    await asyncio.sleep(0)  # let collect() reach queue.get() before publishing
    bus.publish("p1", "job.phase", phase="extracting")
    await asyncio.wait_for(task, timeout=1)

    assert len(events) == 1
    assert events[0].payload == {"phase": "extracting"}


@pytest.mark.asyncio
async def test_catch_up_replays_buffered_events_since_seq() -> None:
    bus = EventBus()
    e1 = bus.publish("p1", "job.phase", phase="a")
    bus.publish("p1", "job.phase", phase="b")
    e3 = bus.publish("p1", "job.phase", phase="c")

    replayed = []
    async for event in bus.subscribe("p1", catch_up_from=e1.seq):
        replayed.append(event)
        if event.seq == e3.seq:
            break

    assert [e.payload["phase"] for e in replayed] == ["b", "c"]


@pytest.mark.asyncio
async def test_catch_up_respects_ring_buffer_size() -> None:
    bus = EventBus(buffer_size=2)
    bus.publish("p1", "job.phase", phase="a")
    bus.publish("p1", "job.phase", phase="b")
    bus.publish("p1", "job.phase", phase="c")

    replayed = []

    async def collect() -> None:
        async for event in bus.subscribe("p1", catch_up_from=0):
            replayed.append(event)
            return

    await asyncio.wait_for(collect(), timeout=1)
    # Only the last 2 survive the ring buffer — "a" is gone.
    assert replayed[0].payload["phase"] == "b"


@pytest.mark.asyncio
async def test_projects_are_isolated() -> None:
    bus = EventBus()
    bus.publish("p1", "job.phase", phase="p1-event")

    events = []

    async def collect() -> None:
        async for event in bus.subscribe("p2"):
            events.append(event)
            return

    task = asyncio.ensure_future(collect())
    await asyncio.sleep(0)  # let collect() reach queue.get() before publishing
    bus.publish("p2", "job.phase", phase="p2-event")
    await asyncio.wait_for(task, timeout=1)

    assert len(events) == 1
    assert events[0].project_id == "p2"


@pytest.mark.asyncio
async def test_full_subscriber_queue_drops_event_without_raising() -> None:
    bus = EventBus()
    channel = bus._channel("p1")
    queue = channel.subscribe()
    for i in range(300):  # exceeds SUBSCRIBER_QUEUE_SIZE
        bus.publish("p1", "job.progress", i=i)

    assert queue.full()
    # Publishing past capacity must not raise for the publisher.
    bus.publish("p1", "job.progress", i=999)


@pytest.mark.asyncio
async def test_unsubscribe_on_generator_close() -> None:
    bus = EventBus()
    channel = bus._channel("p1")

    gen = bus.subscribe("p1")
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0)  # let the generator run up to channel.subscribe()
    bus.publish("p1", "job.phase", phase="x")
    await asyncio.wait_for(task, timeout=1)
    assert len(channel._subscribers) == 1

    await gen.aclose()
    assert len(channel._subscribers) == 0
