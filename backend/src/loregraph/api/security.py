"""Who is allowed to reach which API — the app's first access layer.

The public default trusts loopback: the DM is whoever is on the machine the
app runs on, and players reach it over the LAN with a token. This is written
behind a Protocol so a private build (real accounts, a DM token, SSO) is a new
authenticator, not a rewrite of every router.
"""

import hashlib
import ipaddress
from dataclasses import dataclass
from typing import Annotated, Protocol, cast, runtime_checkable

from fastapi import (
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketException,
    status,
)

# Cookie a play session sets, holding the raw token. HttpOnly so page scripts
# can't read it; the token is exchanged for this cookie at POST /api/play/session
# so <img> and WebSocket subresource requests (which can't set headers) carry it.
PLAY_COOKIE_NAME = "lg_play"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def extract_player_token(request: Request) -> str | None:
    """A play token from the session cookie, or an Authorization: Bearer header
    as a fallback for tests and scripts."""
    cookie = request.cookies.get(PLAY_COOKIE_NAME)
    if cookie:
        return cookie
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header.removeprefix("Bearer ").strip() or None
    return None


@dataclass(frozen=True)
class MasterIdentity:
    """Whoever the active MasterAuthenticator accepts as the DM. Carries no
    fields today (loopback == the DM); a private build can subclass or extend
    the authenticator without changing call sites that only check the type."""


@dataclass(frozen=True)
class PlayerIdentity:
    """An authenticated player, resolved from a play token. project_id comes
    from the token, never from the URL, so a token can't address another
    project."""

    player_id: str
    project_id: str
    name: str


@runtime_checkable
class MasterAuthenticator(Protocol):
    async def identify(self, request: Request) -> MasterIdentity | None: ...
    async def identify_ws(self, websocket: WebSocket) -> MasterIdentity | None: ...


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    # "::ffff:127.0.0.1" and friends: judge the mapped IPv4, not the wrapper.
    if ip.version == 6 and isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


class LoopbackMasterAuthenticator:
    """The DM is whoever is on the machine the app runs on.

    Deliberately does NOT read X-Forwarded-For / X-Real-IP: behind a reverse
    proxy those headers are trivially forged, and "trust loopback" would become
    "trust everyone". Put a real authenticator in front and set
    trust_loopback=false when running behind a proxy."""

    def __init__(self, *, trust_loopback: bool = True) -> None:
        self._trust_loopback = trust_loopback

    async def identify(self, request: Request) -> MasterIdentity | None:
        host = request.client.host if request.client else None
        return self._decide(host)

    async def identify_ws(self, websocket: WebSocket) -> MasterIdentity | None:
        host = websocket.client.host if websocket.client else None
        return self._decide(host)

    def _decide(self, host: str | None) -> MasterIdentity | None:
        if self._trust_loopback and _is_loopback(host):
            return MasterIdentity()
        return None


def get_master_authenticator(request: Request) -> MasterAuthenticator:
    return cast(MasterAuthenticator, request.app.state.master_authenticator)


MasterAuthenticatorDep = Annotated[
    MasterAuthenticator, Depends(get_master_authenticator)
]


async def require_master(
    request: Request, auth: MasterAuthenticatorDep
) -> MasterIdentity:
    identity = await auth.identify(request)
    if identity is None:
        raise HTTPException(status_code=401, detail="Master access required")
    return identity


async def require_master_ws(websocket: WebSocket) -> MasterIdentity:
    # The authenticator is read straight off app.state, not through the HTTP
    # getter: that one is typed for Request, which FastAPI can't supply on a
    # websocket route. HTTPException also wouldn't close a socket cleanly, so
    # WebSocketException gives the client a proper 1008 policy-violation close.
    auth = cast(MasterAuthenticator, websocket.app.state.master_authenticator)
    identity = await auth.identify_ws(websocket)
    if identity is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return identity
