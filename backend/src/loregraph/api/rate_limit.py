"""A small in-process rate limiter for the one endpoint reachable unauthenticated.

Once the port is open to the internet, `POST /api/play/session` is the only
thing an unknown caller can reach that does work. Guessing a token is not the
threat — they are 256 bits — but nothing should be free to hammer: this keeps a
flood from spending the DM's CPU and filling the log, and slows anyone probing.

In-process and per-IP on purpose: single process, single machine, no Redis (the
same reasoning as services/event_bus.py). It is not a defence against a
distributed flood, and does not pretend to be.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# Generous for a real group sitting down to play — a player opens their link a
# handful of times — and cheap for anyone trying to automate against it.
DEFAULT_MAX_ATTEMPTS = 20
DEFAULT_WINDOW_SECONDS = 60.0
# Bound the bookkeeping so a flood from many addresses can't grow memory
# without limit; the oldest idle entries are dropped first.
MAX_TRACKED_CLIENTS = 4096


class RateLimiter:
    """Sliding window of attempts per client address."""

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)

    def check(self, client_ip: str, *, now: float | None = None) -> bool:
        """Record an attempt. False when the caller is over the limit."""
        current = time.monotonic() if now is None else now
        hits = self._hits[client_ip]
        cutoff = current - self._window
        while hits and hits[0] < cutoff:
            hits.popleft()
        if not hits:
            self._evict_idle(cutoff)
        if len(hits) >= self._max_attempts:
            return False
        hits.append(current)
        return True

    def _evict_idle(self, cutoff: float) -> None:
        if len(self._hits) <= MAX_TRACKED_CLIENTS:
            return
        stale = [ip for ip, hits in self._hits.items() if not hits or hits[-1] < cutoff]
        for ip in stale:
            del self._hits[ip]


def client_ip(request: Request) -> str:
    """The peer address. Deliberately not X-Forwarded-For — it is caller-
    supplied, so trusting it would let one client pose as thousands and empty
    the limiter (same reasoning as the master check in api/security.py)."""
    return request.client.host if request.client else "unknown"


def enforce(limiter: RateLimiter, request: Request) -> None:
    if not limiter.check(client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Wait a minute and try again.",
            headers={"Retry-After": str(int(DEFAULT_WINDOW_SECONDS))},
        )
