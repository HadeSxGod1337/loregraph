"""Serving the built frontend from the same process as the API.

One process and one port is what makes the app reachable without ceremony:
a single firewall rule, a single port to forward on a router, and no CORS or
"which host is the backend on" question at all — the page and its API share an
origin. A dev checkout that runs Vite separately just won't have a build here,
and everything still works over two ports.
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# Prefixes owned by the API — never answered with the SPA shell, so a typo'd
# API call gets a real 404 instead of a page that looks like it worked.
_RESERVED_PREFIXES = ("/api", "/files", "/docs", "/redoc", "/openapi.json")


def mount_frontend(app: FastAPI, dist_dir: Path) -> bool:
    """Serve `dist_dir` as the app's frontend. Returns False when there is no
    build to serve (dev checkout), leaving the app API-only."""
    index_path = dist_dir / "index.html"
    if not index_path.is_file():
        logger.info(
            "No frontend build at %s — serving the API only. Run `npm run build` "
            "in frontend/ for the single-port setup.",
            dist_dir,
        )
        return False

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        # Hashed filenames, so these are safe to cache hard.
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    root = dist_dir.resolve()

    # Deliberately sync: this only does blocking stat calls, and FastAPI runs
    # sync handlers in a threadpool — cleaner than awaiting file IO here.
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        """Hand every non-API path to the SPA so client-side routes survive a
        reload or a pasted link — /play/<token> has to work when typed."""
        if ("/" + full_path).startswith(_RESERVED_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")

        # A real file in the build (favicon, manifest, icons) wins over the
        # shell. Resolve-and-contain guards against traversal, since this
        # handler sees raw path segments.
        if full_path:
            candidate = (dist_dir / full_path).resolve()
            if (root == candidate or root in candidate.parents) and candidate.is_file():
                return FileResponse(candidate)

        # index.html must not be cached, or a browser keeps loading the old
        # shell (with stale asset hashes) after an update.
        return FileResponse(index_path, headers={"Cache-Control": "no-store"})

    logger.info("Serving frontend from %s", dist_dir)
    return True
