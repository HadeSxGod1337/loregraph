from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any


def load_plugin_hooks(group: str) -> list[Callable[..., Any]]:
    """Callables registered under `group` by an optionally installed plugin
    package (e.g. a private extension). Empty list when nothing is installed
    — absence of a plugin is not an error."""
    return [ep.load() for ep in entry_points(group=group)]
