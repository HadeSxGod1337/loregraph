from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from loregraph.config import Settings
from loregraph.main import create_app


def _settings(tmp_path: Path, **extra: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "data_dir": tmp_path,
        "embedding_provider": "disabled",
        "_env_file": None,
        **extra,
    }
    return Settings(**kwargs)


def test_plain_http_by_default(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert settings.tls_enabled is False
    assert settings.public_scheme == "http"


def test_both_halves_enable_tls(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path, ssl_certfile=tmp_path / "c.crt", ssl_keyfile=tmp_path / "k.key"
    )
    assert settings.tls_enabled is True
    assert settings.public_scheme == "https"


def test_one_half_alone_is_not_tls(tmp_path: Path) -> None:
    # Serving plain HTTP while the DM believes it is encrypted would be the
    # worst outcome; a half-configured pair must never read as enabled.
    only_cert = _settings(tmp_path, ssl_certfile=tmp_path / "c.crt")
    only_key = _settings(tmp_path, ssl_keyfile=tmp_path / "k.key")
    assert only_cert.tls_enabled is False
    assert only_key.tls_enabled is False
    assert only_cert.public_scheme == "http"


def test_invite_link_follows_the_scheme(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        play_host="192.168.1.5",
        ssl_certfile=tmp_path / "c.crt",
        ssl_keyfile=tmp_path / "k.key",
    )
    with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as client:
        project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
        created = client.post(
            f"/api/projects/{project_id}/players", json={"name": "Kael"}
        ).json()
        assert created["play_url"].startswith("https://192.168.1.5:8000/play/")


def test_invite_link_is_http_without_tls(tmp_path: Path) -> None:
    settings = _settings(tmp_path, play_host="192.168.1.5")
    with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as client:
        project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
        created = client.post(
            f"/api/projects/{project_id}/players", json={"name": "Kael"}
        ).json()
        assert created["play_url"].startswith("http://192.168.1.5:8000/play/")
