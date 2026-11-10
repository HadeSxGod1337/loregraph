"""DM authentication against access tokens issued by the Go auth service.

The Go service signs RS256 access tokens; we verify them locally with the
matching public key — no per-request round-trip to the auth service. The
Protocol it satisfies lives in api/security.py, so routers never learn which
authenticator is wired in.
"""

from pathlib import Path

import jwt
from fastapi import Request, WebSocket

from loregraph.api.security import MasterIdentity, MasterAuthenticator
import time

import httpx


def _extract_bearer(header: str | None) -> str | None:
    if not header:
        return None
    prefix = "Bearer "
    if not header.startswith(prefix):
        return None
    token = header[len(prefix):].strip()
    return token or None


def _fetch_public_key(url: str) -> str:
    """Fetch the PEM-encoded public key from the Go service.

    Retries on connection errors: on a cold start the Go service may still be
    binding its port when the backend comes up, and the two are started by
    different launchers (a batch file, systemd, two terminals) that make no
    ordering guarantees. Ten attempts with one-second spacing is long enough
    to cover a slow bind and short enough that a genuinely missing service
    surfaces as a clear error, not a hang.

    Not retried on a 4xx: a 404 means the route isn't there (wrong URL,
    service built without PublicKeyHandler) and waiting won't change that.
    """
    last_error: Exception | None = None
    for _ in range(10):
        try:
            response = httpx.get(url, timeout=5.0)
            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"server error {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            body = response.text.strip()
            if not body.startswith("-----BEGIN PUBLIC KEY-----"):
                raise ValueError(f"unexpected body from {url}: {body[:64]!r}")
            return body
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
            last_error = exc
            time.sleep(1.0)
    raise RuntimeError(
        f"could not fetch public key from {url} after 10 attempts: {last_error}"
    )


class GoMasterAuthenticator:
    """Verifies Go-service access tokens and accepts users whose `role`
    claim matches the configured master role."""

    def __init__(
            self, *, public_key_pem: str, issuer: str, master_role: str
    ) -> None:
        # Read once: the key doesn't change while the process runs, and a
        # per-request fetch would be pure overhead on the hot path.
        self._public_key = public_key_pem
        self._issuer = issuer
        self._master_role = master_role

    def _verify(self, token: str) -> MasterIdentity | None:
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                # Pin the algorithm: without this, a token signed with HS256
                # using the public key bytes as the HMAC secret would pass.
                algorithms=["RS256"],
                issuer=self._issuer,
                options={"require": ["exp", "iss", "sub", "role"]},
            )
        except jwt.PyJWTError:
            return None
        # Owner and master are both "full access" from Loregraph's point of view —
        # the distinction only matters inside the Go auth service (owners manage
        # accounts, masters run games). Rejecting "owner" here would lock out the
        # one account that exists on a fresh install, since the bootstrap account
        # is always created as owner.
        if claims.get("role") not in ("master", "owner"):
            return None
        return MasterIdentity()

    async def identify(self, request: Request) -> MasterIdentity | None:
        token = _extract_bearer(request.headers.get("Authorization"))
        if token is None:
            return None
        return self._verify(token)

    async def identify_ws(self, websocket: WebSocket) -> MasterIdentity | None:
        token = _extract_bearer(websocket.headers.get("Authorization"))
        if token is None:
            return None
        return self._verify(token)

class GoOrLoopbackMasterAuthenticator:
    """Trust loopback unconditionally, everyone else must present a valid
    Go-issued token. Loopback is the machine the app runs on, so this is the
    'DM at their own desk' case; everything from the network — including
    other devices on the same LAN — has to authenticate.
    """

    def __init__(
        self,
        *,
        loopback: "LoopbackMasterAuthenticator",
        go: GoMasterAuthenticator,
    ) -> None:
        self._loopback = loopback
        self._go = go

    async def identify(self, request: Request) -> MasterIdentity | None:
        identity = await self._loopback.identify(request)
        if identity is not None:
            return identity
        return await self._go.identify(request)

    async def identify_ws(self, websocket: WebSocket) -> MasterIdentity | None:
        identity = await self._loopback.identify_ws(websocket)
        if identity is not None:
            return identity
        return await self._go.identify_ws(websocket)


def go_master_authenticator(settings) -> "MasterAuthenticator":
    from loregraph.api.security import LoopbackMasterAuthenticator

    loopback = LoopbackMasterAuthenticator(trust_loopback=settings.trust_loopback)

    if settings.go_auth_url is None:
        return loopback

    pem = _fetch_public_key(settings.go_auth_url)
    go = GoMasterAuthenticator(
        public_key_pem=pem,
        issuer=settings.go_auth_issuer,
        master_role=settings.go_auth_master_role,
    )
    return GoOrLoopbackMasterAuthenticator(loopback=loopback, go=go)