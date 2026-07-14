from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMCallUsage:
    """Token usage for one model call, cache-aware.

    Follows LangChain's `usage_metadata` convention: `input_tokens` is the
    grand total input, of which `cache_read_tokens`/`cache_creation_tokens`
    are the cached portions (the uncached remainder is
    input_tokens - cache_read - cache_creation). Summing across retry
    attempts is `a + b`.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def __add__(self, other: "LLMCallUsage") -> "LLMCallUsage":
        return LLMCallUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_creation_tokens + other.cache_creation_tokens,
        )


def parse_usage(usage_metadata: Mapping[str, Any] | None) -> LLMCallUsage:
    """Read a LangChain `usage_metadata` dict, including Anthropic cache tokens
    surfaced under `input_token_details.cache_read` / `cache_creation`.

    Defensive against missing/None values: providers that don't report cache
    tokens (OpenAI, Ollama) simply yield zeros."""
    usage = usage_metadata or {}
    details = usage.get("input_token_details") or {}
    return LLMCallUsage(
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_tokens=int(details.get("cache_read") or 0),
        cache_creation_tokens=int(details.get("cache_creation") or 0),
    )
