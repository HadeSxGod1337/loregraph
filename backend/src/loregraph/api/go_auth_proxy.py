"""Server-side proxy to the Go auth service.

In a packaged install the Go service listens on 127.0.0.1:8080 and never
faces the network — the backend is the only thing exposed. The SPA talks to
/api/go-auth/* on its own origin and this route forwards the call, so there
is no second port to open, no second certificate, and no CORS surface to
maintain.

Not used in dev: there VITE_GO_AUTH_URL points the SPA straight at :8080 and
the Go service's own CORS middleware covers the two-origin case. The proxy
exists so the production path can be a single origin without touching the
auth service at all.
"""

from typing import Final

import httpx
from fastapi import APIRouter, Request, Response

GO_AUTH_BASE: Final = "http://127.0.0.1:8080"
_STRIP_HEADERS: Final = frozenset(
    {"host", "content-length", "transfer-encoding", "connection"}
)

router = APIRouter()


@router.api_route(
    "/api/go-auth/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    include_in_schema=False,
)
async def proxy_to_go_auth(request: Request, path: str) -> Response:
    target = f"{GO_AUTH_BASE}/{path}"

    forward_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _STRIP_HEADERS
    }

    body = await request.body()

    async with httpx.AsyncClient(timeout=15.0) as client:
        upstream = await client.request(
            method=request.method,
            url=target,
            headers=forward_headers,
            content=body,
            params=request.query_params,
        )

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _STRIP_HEADERS
    }

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )