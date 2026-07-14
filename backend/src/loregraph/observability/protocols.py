from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RunTraceMetadata:
    project_id: str
    thread_id: str
    run_name: str
    provider: str


@runtime_checkable
class TracingConfig(Protocol):
    def get_run_metadata(
        self, *, project_id: str, thread_id: str, run_name: str
    ) -> RunTraceMetadata: ...


@runtime_checkable
class TracingLifecycle(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
