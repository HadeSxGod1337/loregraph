from fastapi import FastAPI
from fastapi.testclient import TestClient

from loregraph.api.rate_limit import DEFAULT_MAX_ATTEMPTS, RateLimiter


def test_allows_up_to_the_limit_then_refuses() -> None:
    limiter = RateLimiter(max_attempts=3, window_seconds=60)
    assert [limiter.check("1.2.3.4", now=100.0) for _ in range(3)] == [True] * 3
    assert limiter.check("1.2.3.4", now=100.0) is False


def test_the_window_slides() -> None:
    limiter = RateLimiter(max_attempts=2, window_seconds=60)
    limiter.check("1.2.3.4", now=100.0)
    limiter.check("1.2.3.4", now=110.0)
    assert limiter.check("1.2.3.4", now=120.0) is False
    # Once the first two attempts age out, the caller is welcome again.
    assert limiter.check("1.2.3.4", now=175.0) is True


def test_clients_are_counted_separately() -> None:
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    assert limiter.check("1.1.1.1", now=0.0) is True
    assert limiter.check("1.1.1.1", now=0.0) is False
    # One noisy address must not lock the rest of the party out.
    assert limiter.check("2.2.2.2", now=0.0) is True


def test_hammering_the_session_endpoint_is_throttled(
    app: FastAPI, client: TestClient
) -> None:
    # A player's own link works; this is about someone probing the open port.
    with TestClient(app, client=("192.168.1.99", 5)) as lan:
        codes = [
            lan.post("/api/play/session", json={"token": "wrong"}).status_code
            for _ in range(DEFAULT_MAX_ATTEMPTS + 3)
        ]
    assert codes[0] == 401, "a bad token is still just unauthorized"
    assert 429 in codes, "hammering must start being refused"
    assert codes[-1] == 429


def test_a_real_login_still_works_after_a_few_tries(
    app: FastAPI, client: TestClient, project_id: str
) -> None:
    token = client.post(
        f"/api/projects/{project_id}/players", json={"name": "Kael"}
    ).json()["token"]
    with TestClient(app, client=("192.168.1.50", 5)) as lan:
        for _ in range(3):
            lan.post("/api/play/session", json={"token": "wrong"})
        assert lan.post("/api/play/session", json={"token": token}).status_code == 200
