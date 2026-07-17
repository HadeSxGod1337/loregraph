import logging
import os

from loregraph.config import Settings
from loregraph.exceptions import ConfigurationError
from loregraph.observability.protocols import RunTraceMetadata

logger = logging.getLogger(__name__)


class LangSmithConfig:
    def __init__(self, settings: Settings) -> None:
        self._project = settings.langsmith_project

    def get_run_metadata(
        self, *, project_id: str, thread_id: str, run_name: str
    ) -> RunTraceMetadata:
        return RunTraceMetadata(
            project_id=project_id,
            thread_id=thread_id,
            run_name=run_name,
            provider="langsmith",
        )


class LangSmithLifecycle:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.langsmith_api_key
        self._project = settings.langsmith_project

    def start(self) -> None:
        if not self._api_key:
            raise ConfigurationError(
                "tracing_provider is 'langsmith' but "
                "CAMPAIGN_LANGSMITH_API_KEY is not set"
            )
        try:
            import langsmith  # noqa: F401
        except ImportError as e:
            raise ConfigurationError(
                "langsmith package not installed. Run: uv sync --extra langsmith"
            ) from e
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = self._api_key
        os.environ["LANGSMITH_PROJECT"] = self._project
        logger.info("LangSmith tracing enabled (project=%s)", self._project)

    def stop(self) -> None:
        os.environ.pop("LANGSMITH_TRACING", None)
        os.environ.pop("LANGSMITH_API_KEY", None)
        os.environ.pop("LANGSMITH_PROJECT", None)
