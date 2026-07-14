from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class UsageEvent:
    """One recorded model call — the DTO passed to UsageStore.record.

    Internal (never checkpointed or returned to the API as-is), so a frozen
    dataclass rather than a Pydantic model. `input_tokens` is the grand total
    input; `cache_*` are the cached portions of it (see llm/usage.py)."""

    project_id: str
    thread_id: str
    node: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


class UsageRollupRow(BaseModel):
    """Cumulative token spend for one (node, model) slice of a project —
    the unit of the /projects/{id}/usage rollup."""

    node: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
