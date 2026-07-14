from loregraph.config import Settings
from loregraph.observability.protocols import TracingConfig, TracingLifecycle


def create_tracing(
    settings: Settings,
) -> tuple[TracingConfig, TracingLifecycle] | None:
    match settings.tracing_provider:
        case "disabled":
            return None
        case "langsmith":
            from loregraph.observability.langsmith_provider import (
                LangSmithConfig,
                LangSmithLifecycle,
            )

            return LangSmithConfig(settings), LangSmithLifecycle(settings)
        case "langfuse":
            from loregraph.observability.langfuse_provider import (
                LangFuseConfig,
                LangFuseLifecycle,
            )

            return LangFuseConfig(settings), LangFuseLifecycle(settings)
