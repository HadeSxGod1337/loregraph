import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from loregraph.services.event_bus import EventBus


def test_ws_streams_live_events_published_after_connect(app: FastAPI) -> None:
    with (
        TestClient(app) as client,
        client.websocket_connect("/api/ws/projects/p1") as ws,
    ):
        event_bus: EventBus = app.state.event_bus
        event_bus.publish("p1", "job.phase", phase="extracting")
        message = json.loads(ws.receive_text())

    assert message["type"] == "job.phase"
    assert message["project_id"] == "p1"
    assert message["payload"] == {"phase": "extracting"}


def test_ws_catch_up_from_replays_buffered_events(app: FastAPI) -> None:
    with TestClient(app) as client:
        event_bus: EventBus = app.state.event_bus
        e1 = event_bus.publish("p2", "job.phase", phase="a")
        event_bus.publish("p2", "job.phase", phase="b")

        with client.websocket_connect(
            f"/api/ws/projects/p2?catch_up_from={e1.seq}"
        ) as ws:
            message = json.loads(ws.receive_text())

    assert message["payload"] == {"phase": "b"}


def test_ws_projects_are_isolated(app: FastAPI) -> None:
    with (
        TestClient(app) as client,
        client.websocket_connect("/api/ws/projects/p3") as ws,
    ):
        event_bus: EventBus = app.state.event_bus
        event_bus.publish("other-project", "job.phase", phase="should_not_arrive")
        event_bus.publish("p3", "job.phase", phase="should_arrive")
        message = json.loads(ws.receive_text())

    assert message["payload"] == {"phase": "should_arrive"}
