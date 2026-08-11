"""How the app is reachable right now, and what to tell the DM about it.

One object answers both "what address do invite links use" and "why can't my
players connect", so the two can never disagree.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Literal

from loregraph.config import Settings
from loregraph.services.upnp import UpnpClient, UpnpMapping, open_port

logger = logging.getLogger(__name__)

# How far the app is exposed. Each step is an explicit launcher flag, never a
# silent default: local (this machine only) -> lan -> internet.
NetworkReach = Literal["local", "lan", "internet"]

# Re-request the lease well before it expires, so a long session doesn't drop.
LEASE_REFRESH_MARGIN_SECONDS = 300


@dataclass
class NetworkStatus:
    """What the DM needs to know to hand out a working link."""

    reach: NetworkReach
    scheme: str
    host: str
    port: int
    tls: bool
    upnp: UpnpMapping | None = None

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


class NetworkService:
    """Owns the port mapping for the app's lifetime: opens it at startup,
    keeps its lease alive, and removes it on the way out so a closed app never
    leaves a hole pointing at this machine."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: UpnpClient | None = None
        self._refresh_task: asyncio.Task[None] | None = None
        self._port = settings.play_frontend_port
        self.status = NetworkStatus(
            reach="local",
            scheme=settings.public_scheme,
            host=settings.play_host or "127.0.0.1",
            port=self._port,
            tls=settings.tls_enabled,
        )

    async def start(self) -> None:
        settings = self._settings
        if not settings.play_mode_enabled:
            return

        self.status.reach = "lan"
        if not settings.internet_mode_enabled:
            return

        mapping, client = await open_port(self._port)
        self.status.upnp = mapping
        if not mapping.reachable or client is None:
            # Stay on the LAN address: it is the one that still works, and the
            # outcome explains what to do about the rest.
            return

        self._client = client
        self.status.reach = "internet"
        if mapping.external_ip:
            self.status.host = mapping.external_ip
        if mapping.lease_seconds:
            self._refresh_task = asyncio.create_task(
                self._refresh_lease(mapping.lease_seconds)
            )

    async def _refresh_lease(self, lease_seconds: int) -> None:
        """Renew the mapping before it lapses. The lease exists so a crash
        can't leave the port open forever; renewing keeps a long game alive."""
        interval = max(60, lease_seconds - LEASE_REFRESH_MARGIN_SECONDS)
        while True:
            try:
                await asyncio.sleep(interval)
                if self._client is not None:
                    await self._client.add_port_mapping(self._port, lease_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Could not refresh the UPnP lease", exc_info=True)

    async def stop(self) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task
            self._refresh_task = None
        if self._client is not None:
            # Best effort: a router that has already forgotten the mapping (or
            # gone away) must not hold up shutdown.
            try:
                await self._client.delete_port_mapping(self._port)
                logger.info("Removed the UPnP mapping for port %s", self._port)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Could not remove the UPnP mapping for port %s — remove it on "
                    "the router if it lingers.",
                    self._port,
                    exc_info=True,
                )
            self._client = None
