from pathlib import Path

from fastapi.testclient import TestClient

from loregraph.services.update_status import (
    UPDATE_CHANGELOG_FILENAME,
    UPDATE_PREFS_FILENAME,
    UPDATE_STATUS_FILENAME,
    read_key_values,
    write_key_values,
)


def _write_status(data_dir: Path, body: str) -> None:
    (data_dir / UPDATE_STATUS_FILENAME).write_text(body, encoding="utf-8")


def test_version_endpoint_always_answers(client: TestClient) -> None:
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert resp.json()["version"]


def test_status_without_launcher_files_is_unknown(client: TestClient) -> None:
    # Zip install / never-launched: the launcher wrote nothing, and the app
    # must say "can't check" instead of "you're up to date".
    resp = client.get("/api/updates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["git_available"] is False
    assert body["update_available"] is False
    assert body["latest_version"] is None
    assert body["preferences"] == {"mode": "ask", "skipped_versions": []}


def test_status_reports_available_update_with_changelog(
    client: TestClient, tmp_path: Path
) -> None:
    _write_status(
        tmp_path,
        "git_available=1\nworktree_dirty=0\n"
        "current_version=0.2.0\nlatest_version=9.9.9\n"
        "checked_at=2026-08-11T09:12:00Z\n",
    )
    (tmp_path / UPDATE_CHANGELOG_FILENAME).write_text(
        "### Added\n- Player access\n", encoding="utf-8"
    )

    body = client.get("/api/updates").json()
    assert body["git_available"] is True
    assert body["latest_version"] == "9.9.9"
    assert body["update_available"] is True
    assert "Player access" in body["changelog"]
    assert body["checked_at"].startswith("2026-08-11T09:12:00")


def test_skipped_version_is_not_offered(client: TestClient, tmp_path: Path) -> None:
    _write_status(tmp_path, "git_available=1\nlatest_version=9.9.9\n")
    (tmp_path / UPDATE_CHANGELOG_FILENAME).write_text("nope", encoding="utf-8")
    (tmp_path / UPDATE_PREFS_FILENAME).write_text(
        "mode=ask\nskipped_versions=9.9.9,9.9.8\n", encoding="utf-8"
    )

    body = client.get("/api/updates").json()
    assert body["latest_version"] == "9.9.9"
    assert body["update_available"] is False
    # No update on offer means no changelog to show.
    assert body["changelog"] is None


def test_latest_equal_to_current_is_not_an_update(
    client: TestClient, tmp_path: Path
) -> None:
    current = client.get("/api/version").json()["version"]
    _write_status(tmp_path, f"git_available=1\nlatest_version={current}\n")
    assert client.get("/api/updates").json()["update_available"] is False


def test_garbage_status_file_does_not_break_the_endpoint(
    client: TestClient, tmp_path: Path
) -> None:
    # Half-written or hand-mangled file: degrade to "unknown", never 500.
    _write_status(tmp_path, "\x00 not a config\ngit_available=maybe\nchecked_at=soon\n")
    body = client.get("/api/updates").json()
    assert body["git_available"] is False
    assert body["checked_at"] is None


def test_preferences_round_trip(client: TestClient, tmp_path: Path) -> None:
    resp = client.put(
        "/api/updates/preferences",
        json={"mode": "never", "skipped_versions": ["0.3.0"]},
    )
    assert resp.status_code == 200

    # Readable back through the API...
    assert client.get("/api/updates").json()["preferences"] == {
        "mode": "never",
        "skipped_versions": ["0.3.0"],
    }
    # ...and as a flat key=value file the launcher shells can parse.
    written = (tmp_path / UPDATE_PREFS_FILENAME).read_text(encoding="utf-8")
    assert "mode=never" in written
    assert "skipped_versions=0.3.0" in written


def test_invalid_mode_is_rejected(client: TestClient) -> None:
    resp = client.put("/api/updates/preferences", json={"mode": "whenever"})
    assert resp.status_code == 422


def test_unknown_mode_in_file_falls_back_to_ask(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path / UPDATE_PREFS_FILENAME).write_text("mode=yolo\n", encoding="utf-8")
    assert client.get("/api/updates").json()["preferences"]["mode"] == "ask"


def test_key_value_parser_handles_comments_and_equals(tmp_path: Path) -> None:
    path = tmp_path / "sample.conf"
    path.write_text(
        "# a comment\n\nmode=ask\nnote=a=b=c\n  spaced  =  value  \nbroken\n",
        encoding="utf-8",
    )
    assert read_key_values(path) == {
        "mode": "ask",
        "note": "a=b=c",
        "spaced": "value",
    }


def test_key_value_writer_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "out.conf"
    write_key_values(path, {"mode": "auto"}, header="# hi\n")
    assert path.read_text(encoding="utf-8") == "# hi\nmode=auto\n"
    assert list(path.parent.iterdir()) == [path]


def test_missing_file_reads_as_empty(tmp_path: Path) -> None:
    assert read_key_values(tmp_path / "nope.conf") == {}
