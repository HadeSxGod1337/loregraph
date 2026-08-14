"""Provider/model structured-output compatibility policy.

This is deliberately an internal LLM-layer policy rather than a property of
agent nodes.  A graph is built from a fresh Settings snapshot per request, so
resolving capabilities here also makes a settings change take effect on the
next request without a global cache.
"""

from dataclasses import dataclass
from enum import StrEnum


class StructuredOutputStrategy(StrEnum):
    """Ways the structured generator can obtain a typed response."""

    NATIVE = "native"
    JSON_MODE = "json_mode"
    RAW_JSON = "raw_json"


@dataclass(frozen=True)
class ModelCapabilities:
    """Ordered, supported structured-output paths for one configured model."""

    structured_output_strategies: tuple[StructuredOutputStrategy, ...]


DEFAULT_CAPABILITIES = ModelCapabilities(
    (
        StructuredOutputStrategy.NATIVE,
        StructuredOutputStrategy.JSON_MODE,
        StructuredOutputStrategy.RAW_JSON,
    )
)


def resolve_model_capabilities(provider: str, model: str) -> ModelCapabilities:
    """Return the cheapest compatible path known for ``provider``/``model``.

    The generic order preserves the one-call native path.  DeepSeek's
    reasoning models are the important exception: current LangChain documents
    ``deepseek-reasoner`` as not supporting structured output, and DeepSeek V4
    thinking mode rejects the forced ``tool_choice`` used by function-based
    structured output.  Both retain normal conversational reasoning; only the
    structured extraction call changes shape.
    """
    normalized_provider = provider.casefold()
    normalized_model = model.casefold()
    if normalized_provider != "deepseek":
        return DEFAULT_CAPABILITIES
    if "reasoner" in normalized_model:
        return ModelCapabilities((StructuredOutputStrategy.RAW_JSON,))
    if "v4" in normalized_model:
        return ModelCapabilities(
            (StructuredOutputStrategy.JSON_MODE, StructuredOutputStrategy.RAW_JSON)
        )
    return DEFAULT_CAPABILITIES
