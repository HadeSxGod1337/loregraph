import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/projects/{project_id}")
async def project_events_ws(websocket: WebSocket, project_id: str) -> None:
    """Server-push only: the client's sole input is the `catch_up_from`
    query param on (re)connect, so a dropped connection can resume without
    missing events still in the per-project ring buffer (see
    services/event_bus.py). No commands travel over this socket — writes
    stay on the existing REST endpoints (send message, resume review,
    upload knowledge source, …); this is purely the read side."""
    event_bus = websocket.app.state.event_bus
    catch_up_from: int | None = None
    raw = websocket.query_params.get("catch_up_from")
    if raw is not None:
        with contextlib.suppress(ValueError):
            catch_up_from = int(raw)

    await websocket.accept()
    try:
        async with contextlib.aclosing(
            event_bus.subscribe(project_id, catch_up_from=catch_up_from)
        ) as events:
            async for event in events:
                await websocket.send_text(event.model_dump_json())
    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected for project %s", project_id)
