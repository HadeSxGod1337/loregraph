import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class AsyncClosable(Protocol):
    async def aclose(self) -> None: ...


class ConnectorRuntime:
    """App-lifetime cache of long-lived per-connection clients (e.g. a Foundry
    MCP ClientSession that owns a spawned Node process). Everything else in
    the app is request-scoped; this is the one deliberate exception, created
    and closed in main.py's lifespan.

    Keys are connection ids; the connections router invalidates an entry
    whenever its connection is updated or deleted, so a config change always
    produces a fresh client on next use.
    """

    def __init__(self) -> None:
        self._clients: dict[str, AsyncClosable] = {}
        self._lock = asyncio.Lock()

    async def get_or_create[T: AsyncClosable](
        self, connection_id: str, factory: Callable[[], Awaitable[T]]
    ) -> T:
        async with self._lock:
            client = self._clients.get(connection_id)
            if client is None:
                client = await factory()
                self._clients[connection_id] = client
            # The cache is homogeneous per connection id (one connector type
            # per connection), so this cast-free narrow is safe in practice.
            return client  # type: ignore[return-value]

    async def invalidate(self, connection_id: str) -> None:
        async with self._lock:
            client = self._clients.pop(connection_id, None)
        if client is not None:
            await self._close_safely(connection_id, client)

    async def aclose(self) -> None:
        async with self._lock:
            clients = dict(self._clients)
            self._clients.clear()
        for connection_id, client in clients.items():
            await self._close_safely(connection_id, client)

    async def _close_safely(self, connection_id: str, client: AsyncClosable) -> None:
        try:
            await client.aclose()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Failed to close connector client for connection %s",
                connection_id,
                exc_info=True,
            )
