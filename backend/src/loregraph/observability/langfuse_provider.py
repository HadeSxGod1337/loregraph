import logging

from loregraph.config import Settings
from loregraph.exceptions import ConfigurationError
from loregraph.observability.protocols import RunTraceMetadata

logger = logging.getLogger(__name__)


class LangFuseConfig:
    def __init__(self, settings: Settings) -> None:
        self._host = settings.langfuse_host

    def get_run_metadata(
        self, *, project_id: str, thread_id: str, run_name: str
    ) -> RunTraceMetadata:
        return RunTraceMetadata(
            project_id=project_id,
            thread_id=thread_id,
            run_name=run_name,
            provider="langfuse",
        )


class LangFuseLifecycle:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._handler = None

    def start(self) -> None:
        if not self._settings.langfuse_public_key:
            raise ConfigurationError(
                "tracing_provider is 'langfuse' but "
                "CAMPAIGN_LANGFUSE_PUBLIC_KEY is not set"
            )
        try:
            from langfuse.callback import CallbackHandler
        except ImportError as e:
            raise ConfigurationError(
                "langfuse package not installed. "
                "Run: uv sync --extra langfuse"
            ) from e
        self._handler = CallbackHandler(
            public_key=self._settings.langfuse_public_key,
            secret_key=self._settings.langfuse_secret_key or "",
            host=self._settings.langfuse_host,
        )
        logger.info("LangFuse tracing enabled")

    def stop(self) -> None:
        if self._handler is not None:
            self._handler.flush()
