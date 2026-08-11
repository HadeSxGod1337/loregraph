"""Entry point the launcher scripts use to run the app.

The bind address is a launch decision (the `--lan` flag), so it arrives as an
argument; everything else — notably TLS — comes from Settings, so the two
launcher scripts never have to parse `.env` themselves and can't drift apart.
"""

import argparse
import logging
import os
import sys

import uvicorn

from loregraph.config import Settings

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="loregraph-serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    settings = Settings()
    logging.basicConfig(level=settings.log_level)

    ssl_certfile = settings.ssl_certfile
    ssl_keyfile = settings.ssl_keyfile
    if (ssl_certfile is None) != (ssl_keyfile is None):
        # One half alone would silently fall back to plain HTTP while the DM
        # believes the connection is encrypted — refuse instead.
        sys.exit(
            "TLS needs both CAMPAIGN_SSL_CERTFILE and CAMPAIGN_SSL_KEYFILE; "
            "only one is set."
        )
    for label, path in (("certificate", ssl_certfile), ("key", ssl_keyfile)):
        if path is not None and not path.is_file():
            sys.exit(f"TLS {label} not found: {path}")

    if ssl_certfile is not None:
        logger.info("TLS enabled, serving https on %s:%s", args.host, args.port)

    # Invite links must name the port we actually bound, or a non-default port
    # silently produces links nobody can open. An explicit setting still wins —
    # behind a reverse proxy the public port differs from the internal one.
    if "play_frontend_port" not in settings.model_fields_set:
        os.environ["CAMPAIGN_PLAY_FRONTEND_PORT"] = str(args.port)

    uvicorn.run(
        "loregraph.main:app",
        host=args.host,
        port=args.port,
        ssl_certfile=str(ssl_certfile) if ssl_certfile else None,
        ssl_keyfile=str(ssl_keyfile) if ssl_keyfile else None,
    )
