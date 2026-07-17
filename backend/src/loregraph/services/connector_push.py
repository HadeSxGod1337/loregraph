"""Auto-push freshly committed lore to connections that opted in.

This is a service-level hook, deliberately NOT a graph node: a push node
would change the checkpointed graph topology (the app's stability contract),
couple the platform-independent agent core to connectors, and put an
external network call inside the HITL pipeline. Instead the runner calls
this after a turn ends with a commit — push runs strictly after commit,
which runs strictly after the DM's approve, so the HITL invariant stands.

A failed push never fails the run: the lore is already safely in canon; the
DM gets an export_push_failed event and can export manually.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.protocols import CAPABILITY_EXPORT, Exporter
from loregraph.connectors.registry import ConnectorRegistry
from loregraph.exceptions import error_code
from loregraph.schemas.connection import ConnectionOut, ExportRequest
from loregraph.storage.protocols import ConnectionStore

logger = logging.getLogger(__name__)

PUSH_TIMEOUT_S = 60.0


class ConnectorPushService:
    def __init__(
        self,
        connection_store: ConnectionStore,
        registry: ConnectorRegistry,
        context_builder: Callable[[ConnectionOut], ConnectorContext],
    ) -> None:
        self._connections = connection_store
        self._registry = registry
        self._context_builder = context_builder

    async def push_after_commit(
        self, project_id: str, entity_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Export the given entities through every auto-push connection.
        Returns SSE-shaped events (export_pushed / export_push_failed) for
        the runner to relay; never raises except on cancellation."""
        if not entity_ids:
            return []
        events: list[dict[str, Any]] = []
        connections = await self._connections.list_for_project(project_id)
        for connection in connections:
            if not connection.auto_push_after_commit:
                continue
            descriptor = self._registry.get(connection.connector_type)
            if CAPABILITY_EXPORT not in descriptor.capabilities:
                continue
            try:
                connector = self._registry.create(
                    connection.connector_type,
                    connection.config,
                    self._context_builder(connection),
                )
                if not isinstance(connector, Exporter):
                    continue
                async with asyncio.timeout(PUSH_TIMEOUT_S):
                    result = await connector.export(
                        ExportRequest(entity_ids=entity_ids)
                    )
                events.append(
                    {
                        "type": "export_pushed",
                        "connection": connection.name,
                        "created": result.created,
                        "updated": result.updated,
                        "errors": len(result.errors),
                    }
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    "Auto-push to connection %s failed",
                    connection.name,
                    exc_info=True,
                )
                events.append(
                    {
                        "type": "export_push_failed",
                        "connection": connection.name,
                        "code": error_code(e),
                    }
                )
        return events
