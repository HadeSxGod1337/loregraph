"""load_plugin_hooks is the only thing standing between the public app and an
optionally installed plugin package — no network, no real private package
needed here, just importlib.metadata's entry_points() lookup mocked out."""

from collections.abc import Callable
from typing import Any

import pytest

from loregraph.plugins.discovery import load_plugin_hooks


def test_returns_empty_list_when_no_plugin_installed() -> None:
    assert load_plugin_hooks("loregraph.tests.nonexistent_group") == []


def test_loads_callables_from_registered_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_register(registry: object) -> None:
        pass

    class FakeEntryPoint:
        def load(self) -> Callable[..., Any]:
            return fake_register

    def fake_entry_points(*, group: str) -> list[FakeEntryPoint]:
        assert group == "loregraph.plugins.connectors"
        return [FakeEntryPoint()]

    monkeypatch.setattr("loregraph.plugins.discovery.entry_points", fake_entry_points)

    hooks = load_plugin_hooks("loregraph.plugins.connectors")

    assert hooks == [fake_register]
