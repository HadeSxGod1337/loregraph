from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loregraph.config import Settings
from loregraph.main import create_app


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app shell</html>", encoding="utf-8")
    (dist / "assets" / "main-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return dist


@pytest.fixture
def spa_client(tmp_path: Path, dist_dir: Path) -> TestClient:
    kwargs: dict[str, Any] = {
        "data_dir": tmp_path / "data",
        "embedding_provider": "disabled",
        "frontend_dist": dist_dir,
        "_env_file": None,
    }
    return TestClient(create_app(Settings(**kwargs)), client=("127.0.0.1", 50000))


def test_root_serves_the_app_shell(spa_client: TestClient) -> None:
    with spa_client as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "app shell" in resp.text
        # index.html must never be cached, or a browser keeps the old shell
        # (with stale asset hashes) after an update.
        assert resp.headers["cache-control"] == "no-store"


def test_client_routes_survive_a_reload(spa_client: TestClient) -> None:
    # A pasted play link has to work: the server knows nothing about /play,
    # so it must hand the path to the SPA rather than 404.
    with spa_client as client:
        for path in ("/play/sometoken", "/projects/abc/graph", "/deep/nested/route"):
            resp = client.get(path)
            assert resp.status_code == 200, path
            assert "app shell" in resp.text


def test_real_build_files_win_over_the_shell(spa_client: TestClient) -> None:
    with spa_client as client:
        assert client.get("/assets/main-abc123.js").text == "console.log(1)"
        assert client.get("/favicon.svg").text == "<svg/>"


def test_api_paths_are_not_swallowed(spa_client: TestClient) -> None:
    with spa_client as client:
        # Real endpoint still answers as itself...
        assert client.get("/api/health").json() == {"status": "ok"}
        # ...and an unknown API path is a real 404, not the app shell.
        resp = client.get("/api/nope")
        assert resp.status_code == 404
        assert "app shell" not in resp.text
        assert client.get("/files/nope/nope.png").status_code == 404


def test_traversal_out_of_the_build_is_refused(spa_client: TestClient) -> None:
    # The handler sees raw path segments, so containment is its own job.
    resp = spa_client.get("/..%2f..%2fcampaign.sqlite3")
    assert resp.status_code in (200, 404)
    assert "sqlite" not in resp.text.lower()


def test_app_without_a_build_is_api_only(tmp_path: Path) -> None:
    # A dev checkout that only ever ran `vite` has no dist — the API must
    # still come up rather than failing at import time.
    kwargs: dict[str, Any] = {
        "data_dir": tmp_path / "data",
        "embedding_provider": "disabled",
        "frontend_dist": tmp_path / "nothing-here",
        "_env_file": None,
    }
    with TestClient(
        create_app(Settings(**kwargs)), client=("127.0.0.1", 50000)
    ) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 404
