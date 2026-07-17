"""Live external sources for the agent.

A LiveSourceProvider is built per request (api/deps.py) from the project's
connections whose connector implements LiveSource. The agent gets one
generic ``query_external_source`` tool over all of them — per-connector
tools would bloat every assistant call's prompt, and the set of sources is
per-project anyway.
"""

from dataclasses import dataclass

from loregraph.connectors.protocols import LiveSource


@dataclass(frozen=True)
class LiveSourceEntry:
    name: str
    connector_type: str
    use_for_grounding: bool
    source: LiveSource


class LiveSourceProvider:
    def __init__(self, entries: list[LiveSourceEntry]) -> None:
        self._entries = list(entries)

    def entries(self) -> list[LiveSourceEntry]:
        return list(self._entries)

    def names(self) -> list[str]:
        return [entry.name for entry in self._entries]

    def get(self, name: str) -> LiveSourceEntry | None:
        needle = name.strip().lower()
        for entry in self._entries:
            if entry.name.strip().lower() == needle:
                return entry
        return None

    def grounding_entries(self) -> list[LiveSourceEntry]:
        return [entry for entry in self._entries if entry.use_for_grounding]

    def describe(self) -> str:
        """One line per source for the system prompt."""
        return "\n".join(
            f"- {entry.name} ({entry.connector_type})" for entry in self._entries
        )

    def __bool__(self) -> bool:
        return bool(self._entries)
