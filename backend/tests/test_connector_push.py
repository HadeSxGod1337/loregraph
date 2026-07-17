from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.protocols import CAPABILITY_EXPORT
from loregraph.connectors.registry import ConnectorDescriptor, ConnectorRegistry
from loregraph.schemas.connection import (
    ConnectionOut,
    ExportPreview,
    ExportRequest,
    ExportResult,
)
from loregraph.services.connector_push import ConnectorPushService


class _EmptyConfig(BaseModel):
    pass


class RecordingExporter:
    def __init__(self) -> None:
        self.requests: list[ExportRequest] = []

    async def preview_export(self, request: ExportRequest) -> ExportPreview:
        return ExportPreview(items=[])

    async def export(self, request: ExportRequest) -> ExportResult:
        self.requests.append(request)
        return ExportResult(created=len(request.entity_ids or []))


class ExplodingExporter:
    async def preview_export(self, request: ExportRequest) -> ExportPreview:
        return ExportPreview(items=[])

    async def export(self, request: ExportRequest) -> ExportResult:
        raise RuntimeError("vault on fire")


class FakeConnectionStore:
    def __init__(self, connections: list[ConnectionOut]) -> None:
        self._connections = connections

    async def list_for_project(self, project_id: str) -> list[ConnectionOut]:
        return [c for c in self._connections if c.project_id == project_id]

    async def create(self, project_id: str, data: object) -> ConnectionOut:
        raise NotImplementedError

    async def get(self, connection_id: str) -> ConnectionOut:
        raise NotImplementedError

    async def update(self, connection_id: str, data: object) -> ConnectionOut:
        raise NotImplementedError

    async def delete(self, connection_id: str) -> None:
        raise NotImplementedError


def _connection(name: str, *, auto_push: bool) -> ConnectionOut:
    now = datetime.now(UTC)
    return ConnectionOut(
        id=f"conn-{name}",
        project_id="p1",
        connector_type="fake",
        name=name,
        config={},
        use_for_grounding=False,
        auto_push_after_commit=auto_push,
        created_at=now,
        updated_at=now,
    )


def _registry(exporter: object) -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(
        ConnectorDescriptor(
            connector_type="fake",
            config_model=_EmptyConfig,
            factory=lambda config, context: exporter,
            capabilities=frozenset({CAPABILITY_EXPORT}),
        )
    )
    return registry


def _context_builder(connection: ConnectionOut) -> ConnectorContext:
    # The fake exporter never touches the context — a placeholder is enough.
    return ConnectorContext(
        project_id=connection.project_id,
        connection_id=connection.id,
        connection_name=connection.name,
        entity_service=None,  # type: ignore[arg-type]
        edge_service=None,  # type: ignore[arg-type]
        entity_store=None,  # type: ignore[arg-type]
        edge_store=None,  # type: ignore[arg-type]
        attachment_store=None,  # type: ignore[arg-type]
        attachments_dir=None,  # type: ignore[arg-type]
        link_store=None,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_push_exports_only_to_opted_in_connections() -> None:
    exporter = RecordingExporter()
    store = FakeConnectionStore(
        [
            _connection("on", auto_push=True),
            _connection("off", auto_push=False),
        ]
    )
    service = ConnectorPushService(store, _registry(exporter), _context_builder)

    events = await service.push_after_commit("p1", ["e1", "e2"])

    assert len(exporter.requests) == 1
    assert exporter.requests[0].entity_ids == ["e1", "e2"]
    assert events == [
        {
            "type": "export_pushed",
            "connection": "on",
            "created": 2,
            "updated": 0,
            "errors": 0,
        }
    ]


@pytest.mark.asyncio
async def test_push_failure_yields_event_never_raises() -> None:
    store = FakeConnectionStore([_connection("broken", auto_push=True)])
    service = ConnectorPushService(
        store, _registry(ExplodingExporter()), _context_builder
    )

    events = await service.push_after_commit("p1", ["e1"])

    assert events[0]["type"] == "export_push_failed"
    assert events[0]["connection"] == "broken"


@pytest.mark.asyncio
async def test_push_with_no_new_entities_is_a_noop() -> None:
    exporter = RecordingExporter()
    store = FakeConnectionStore([_connection("on", auto_push=True)])
    service = ConnectorPushService(store, _registry(exporter), _context_builder)

    assert await service.push_after_commit("p1", []) == []
    assert exporter.requests == []
