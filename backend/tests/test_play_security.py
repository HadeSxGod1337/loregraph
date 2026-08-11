import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loregraph.api.security import LoopbackMasterAuthenticator, _is_loopback


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("::ffff:127.0.0.1", True),
        ("192.168.1.50", False),
        ("10.0.0.4", False),
        ("testclient", False),  # Starlette's default, not an IP
        (None, False),
    ],
)
def test_is_loopback(host: str | None, expected: bool) -> None:
    assert _is_loopback(host) is expected


def _non_loopback_client(app: FastAPI) -> TestClient:
    return TestClient(app, client=("192.168.1.50", 1234))


def test_loopback_caller_is_the_master(client: TestClient) -> None:
    # The default fixture pins 127.0.0.1 — the whole existing suite proves
    # this path; one explicit assertion documents the contract.
    assert client.get("/api/projects").status_code == 200


def test_non_loopback_caller_is_rejected(app: FastAPI) -> None:
    with _non_loopback_client(app) as lan:
        assert lan.get("/api/projects").status_code == 401


def test_health_and_version_stay_open(app: FastAPI) -> None:
    with _non_loopback_client(app) as lan:
        assert lan.get("/api/health").status_code == 200
        assert lan.get("/api/version").status_code == 200


def test_forwarded_header_cannot_forge_loopback(app: FastAPI) -> None:
    # Behind a proxy, X-Forwarded-For is attacker-controlled; the authenticator
    # judges the real peer address only, so a spoofed header changes nothing.
    with _non_loopback_client(app) as lan:
        resp = lan.get("/api/projects", headers={"X-Forwarded-For": "127.0.0.1"})
        assert resp.status_code == 401


def test_websocket_rejects_non_loopback(app: FastAPI) -> None:
    from starlette.websockets import WebSocketDisconnect as StarletteWsDisconnect

    with _non_loopback_client(app) as lan:
        with pytest.raises(StarletteWsDisconnect) as excinfo:
            with lan.websocket_connect("/api/ws/projects/whatever"):
                pass
    assert excinfo.value.code == 1008


def test_docs_disabled_in_play_mode() -> None:
    from loregraph.config import Settings
    from loregraph.main import create_app

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        embedding_provider="disabled",
        play_mode_enabled=True,
    )
    with TestClient(create_app(settings), client=("127.0.0.1", 5)) as dm:
        assert dm.get("/docs").status_code == 404
        assert dm.get("/openapi.json").status_code == 404
        # The app still works — only the API map is hidden.
        assert dm.get("/api/health").status_code == 200


@pytest.mark.asyncio
async def test_trust_loopback_off_rejects_loopback() -> None:
    # Behind a reverse proxy the peer address is the proxy, so loopback trust
    # must be switchable off — then even 127.0.0.1 is not the master.
    from types import SimpleNamespace

    auth = LoopbackMasterAuthenticator(trust_loopback=False)
    # A stand-in for starlette.requests.Request — identify only touches .client.
    fake = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    assert await auth.identify(fake) is None  # type: ignore[arg-type]
