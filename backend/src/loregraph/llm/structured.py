import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, cast, runtime_checkable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from loregraph.exceptions import GenerationError
from loregraph.llm.capabilities import (
    DEFAULT_CAPABILITIES,
    ModelCapabilities,
    StructuredOutputStrategy,
)
from loregraph.llm.usage import LLMCallUsage, parse_usage

MAX_STRUCTURED_ATTEMPTS = 3
MAX_TRANSPORT_ATTEMPTS = 2
TRANSPORT_RETRY_DELAY_SECONDS = 0.25

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StructuredResult[T]:
    value: T
    # Summed across schema-validation retries; cache-aware (see llm/usage.py).
    usage: LLMCallUsage


@runtime_checkable
class StructuredGenerator(Protocol):
    """One structured LLM call with schema validation and usage accounting.

    A deliberate seam between agent nodes and LangChain: nodes are tested
    with fakes of this Protocol instead of fake chat models, and the
    retry-on-invalid-schema loop lives in exactly one place (DRY per
    CLAUDE.md: retries and schema validation are shared helpers).

    `cached_prefix` is the stable head of the user prompt: when the underlying
    model supports Anthropic prompt caching, it is sent as a cached content
    block so regenerations (retry/revision) reuse it at ~0.1x. Providers
    without caching just see it concatenated with `user`."""

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]: ...


class LangChainStructuredGenerator:
    def __init__(
        self,
        model: BaseChatModel,
        *,
        prompt_caching: bool = False,
        max_attempts: int = MAX_STRUCTURED_ATTEMPTS,
        capabilities: ModelCapabilities = DEFAULT_CAPABILITIES,
        provider: str | None = None,
        model_name: str | None = None,
        max_transport_attempts: int = MAX_TRANSPORT_ATTEMPTS,
        transport_retry_delay_seconds: float = TRANSPORT_RETRY_DELAY_SECONDS,
    ) -> None:
        self._model = model
        self._prompt_caching = prompt_caching
        self._max_attempts = max_attempts
        self._capabilities = capabilities
        self._provider = provider or "unknown"
        self._model_name = model_name or "unknown"
        self._max_transport_attempts = max_transport_attempts
        self._transport_retry_delay_seconds = transport_retry_delay_seconds

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        prior_usage = LLMCallUsage()
        last_capability_error: Exception | None = None
        strategies = self._capabilities.structured_output_strategies
        for index, strategy in enumerate(strategies):
            try:
                result = await self._generate_with_strategy(
                    strategy,
                    schema,
                    system=system,
                    user=user,
                    cached_prefix=cached_prefix,
                )
                return StructuredResult(result.value, prior_usage + result.usage)
            except _CapabilityFailure as failure:
                prior_usage += failure.usage
                last_capability_error = failure.cause
                if index + 1 == len(strategies):
                    break
                next_strategy = strategies[index + 1]
                logger.debug(
                    "Structured-output compatibility fallback provider=%s model=%s "
                    "from_strategy=%s to_strategy=%s classification=%s "
                    "strategy_attempt=%d",
                    self._provider,
                    self._model_name,
                    strategy,
                    next_strategy,
                    RequestErrorKind.CAPABILITY,
                    index + 1,
                    exc_info=True,
                )
        raise GenerationError(
            f"No compatible structured-output strategy returned a valid "
            f"{schema.__name__} for provider {self._provider!r} and model "
            f"{self._model_name!r}"
        ) from last_capability_error

    async def _generate_with_strategy[T: BaseModel](
        self,
        strategy: StructuredOutputStrategy,
        schema: type[T],
        *,
        system: str,
        user: str,
        cached_prefix: str,
    ) -> StructuredResult[T]:
        messages: list[BaseMessage] = [
            SystemMessage(self._system_message(system, schema, strategy)),
            self._user_message(cached_prefix, user),
        ]
        usage = LLMCallUsage()
        last_error = "no response"
        try:
            invoke = self._strategy_invoke(strategy, schema)
        except Exception as exc:
            if classify_request_error(exc) is RequestErrorKind.CAPABILITY:
                raise _CapabilityFailure(exc, usage) from exc
            raise self._provider_error(schema, exc) from exc

        for _ in range(self._max_attempts):
            response, attempt_usage = await self._invoke_with_transport(
                invoke, messages
            )
            usage += attempt_usage
            raw_message, parsed, parsing_error = self._parse_strategy_response(
                strategy, schema, response
            )
            usage += parse_usage(raw_message.usage_metadata)
            if parsed is not None:
                return StructuredResult(parsed, usage)
            last_error = parsing_error
            # This is a schema retry, not a provider compatibility retry: the
            # request was accepted and returned a concrete model response.
            messages = [
                *messages,
                raw_message,
                HumanMessage(
                    f"Your previous response failed schema validation: "
                    f"{last_error}. Respond again as a valid {schema.__name__} "
                    "JSON object only."
                ),
            ]
        raise GenerationError(
            f"LLM did not return a valid {schema.__name__} after "
            f"{self._max_attempts} schema attempts: {last_error}"
        )

    def _strategy_invoke[T: BaseModel](
        self, strategy: StructuredOutputStrategy, schema: type[T]
    ) -> Callable[[list[BaseMessage]], Awaitable[object]]:
        if strategy is StructuredOutputStrategy.RAW_JSON:
            return self._model.ainvoke
        kwargs: dict[str, Any] = {"include_raw": True}
        if strategy is StructuredOutputStrategy.JSON_MODE:
            kwargs["method"] = "json_mode"
        runnable = self._model.with_structured_output(schema, **kwargs)
        return runnable.ainvoke

    async def _invoke_with_transport(
        self,
        invoke: Callable[[list[BaseMessage]], Awaitable[object]],
        messages: list[BaseMessage],
    ) -> tuple[object, LLMCallUsage]:
        usage = LLMCallUsage()
        for attempt in range(self._max_transport_attempts):
            try:
                return await invoke(messages), usage
            except Exception as exc:
                usage += _usage_from_exception(exc)
                kind = classify_request_error(exc)
                if kind is RequestErrorKind.CAPABILITY:
                    raise _CapabilityFailure(exc, usage) from exc
                if kind is RequestErrorKind.TRANSIENT and (
                    attempt + 1 < self._max_transport_attempts
                ):
                    delay = self._transport_retry_delay_seconds * (2**attempt)
                    logger.debug(
                        "Retrying transient structured-output request provider=%s "
                        "model=%s attempt=%d delay_seconds=%s",
                        self._provider,
                        self._model_name,
                        attempt + 1,
                        delay,
                        exc_info=True,
                    )
                    if delay:
                        await asyncio.sleep(delay)
                    continue
                raise self._provider_error(None, exc) from exc
        raise AssertionError("transport retry loop must return or raise")

    def _parse_strategy_response[T: BaseModel](
        self, strategy: StructuredOutputStrategy, schema: type[T], response: object
    ) -> tuple[AIMessage, T | None, str]:
        if strategy is StructuredOutputStrategy.RAW_JSON:
            raw_message = _as_ai_message(response)
            try:
                value = schema.model_validate_json(_json_text(raw_message))
            except (
                ValidationError,
                ValueError,
                TypeError,
                json.JSONDecodeError,
            ) as exc:
                return raw_message, None, str(exc)
            return raw_message, value, ""

        result = cast(dict[str, Any], response)
        raw_message = _as_ai_message(result.get("raw"))
        parsed = result.get("parsed")
        if parsed is None:
            return (
                raw_message,
                None,
                str(result.get("parsing_error") or "no parsed value"),
            )
        try:
            return raw_message, schema.model_validate(parsed), ""
        except (ValidationError, ValueError, TypeError) as exc:
            return raw_message, None, str(exc)

    def _system_message[T: BaseModel](
        self, system: str, schema: type[T], strategy: StructuredOutputStrategy
    ) -> str:
        if strategy is StructuredOutputStrategy.NATIVE:
            return system
        schema_json = json.dumps(
            schema.model_json_schema(), ensure_ascii=False, sort_keys=True
        )
        return (
            f"{system}\n\nReturn only a JSON object that validates against this "
            f"JSON Schema:\n{schema_json}"
        )

    def _provider_error(
        self, schema: type[BaseModel] | None, exc: Exception
    ) -> GenerationError:
        target = schema.__name__ if schema is not None else "structured response"
        return GenerationError(
            f"LLM request for {target} failed for provider {self._provider!r} "
            f"and model {self._model_name!r}: {type(exc).__name__}"
        )

    def _user_message(self, cached_prefix: str, user: str) -> HumanMessage:
        """The user turn, with a prompt-caching breakpoint on the stable prefix
        when supported. The breakpoint caches tools + system + `cached_prefix`
        (render order is tools → system → messages), leaving the volatile
        `user` tail uncached — so retries pay full price only on what changed."""
        if not cached_prefix:
            return HumanMessage(user)
        if not self._prompt_caching:
            return HumanMessage(
                "\n".join(part for part in (cached_prefix, user) if part)
            )
        content: list[str | dict[str, Any]] = [
            {
                "type": "text",
                "text": cached_prefix,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if user:
            content.append({"type": "text", "text": user})
        return HumanMessage(content)


class RequestErrorKind(StrEnum):
    CAPABILITY = "capability"
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class _CapabilityFailure(Exception):
    cause: Exception
    usage: LLMCallUsage


_CAPABILITY_ERROR_MARKERS = (
    "thinking mode does not support this tool_choice",
    "tool_choice",
    "response_format",
    "json_schema",
    "json schema is not supported",
    "does not support structured output",
    "does not support function calling",
    "unsupported structured output",
)
_LOCAL_CAPABILITY_ERROR_MARKERS = (
    "unsupported method",
    "unrecognized method",
    "unexpected keyword argument 'method'",
    'unexpected keyword argument "method"',
)
_AUTH_ERROR_MARKERS = (
    "invalid api key",
    "incorrect api key",
    "authentication",
    "unauthorized",
    "forbidden",
)
_TRANSIENT_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "temporarily unavailable",
    "service unavailable",
    "rate limit",
    "too many requests",
)


def classify_request_error(exc: Exception) -> RequestErrorKind:
    """Classify a provider failure once, with deliberately narrow markers."""
    status = _status_code(exc)
    message = str(exc).casefold()
    if status in {401, 403} or any(marker in message for marker in _AUTH_ERROR_MARKERS):
        return RequestErrorKind.PERMANENT
    if status in {429, 500, 502, 503, 504} or isinstance(exc, TimeoutError):
        return RequestErrorKind.TRANSIENT
    if any(marker in message for marker in _TRANSIENT_ERROR_MARKERS):
        return RequestErrorKind.TRANSIENT
    if isinstance(exc, (NotImplementedError, AttributeError)):
        return RequestErrorKind.CAPABILITY
    if any(marker in message for marker in _LOCAL_CAPABILITY_ERROR_MARKERS):
        return RequestErrorKind.CAPABILITY
    if status in {400, 404, 422} and any(
        marker in message for marker in _CAPABILITY_ERROR_MARKERS
    ):
        return RequestErrorKind.CAPABILITY
    return RequestErrorKind.UNKNOWN


def _status_code(exc: Exception) -> int | None:
    direct = getattr(exc, "status_code", None)
    if isinstance(direct, int):
        return direct
    response = getattr(exc, "response", None)
    nested = getattr(response, "status_code", None)
    return nested if isinstance(nested, int) else None


def _usage_from_exception(exc: Exception) -> LLMCallUsage:
    """Keep provider-reported usage from failed attempts when it is exposed."""
    candidates = [
        getattr(exc, "usage_metadata", None),
        getattr(getattr(exc, "response", None), "usage_metadata", None),
        getattr(getattr(exc, "response", None), "usage", None),
    ]
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            if "input_tokens" in candidate or "output_tokens" in candidate:
                return parse_usage(candidate)
            return LLMCallUsage(
                input_tokens=int(candidate.get("prompt_tokens") or 0),
                output_tokens=int(candidate.get("completion_tokens") or 0),
            )
    return LLMCallUsage()


def _as_ai_message(response: object) -> AIMessage:
    if isinstance(response, AIMessage):
        return response
    raise GenerationError(
        "LLM structured-output response did not include an AI message"
    )


def _json_text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return _strip_json_fence(content)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                raise ValueError("LLM response did not contain plain JSON text")
            text = block.get("text")
            if not isinstance(text, str):
                raise ValueError("LLM text block did not contain text")
            parts.append(text)
        return _strip_json_fence("".join(parts))
    raise ValueError("LLM response did not contain text")


def _strip_json_fence(text: str) -> str:
    """Remove only a complete, conventional Markdown JSON fence."""
    stripped = text.strip()
    if not (stripped.startswith("```") and stripped.endswith("```")):
        return stripped
    opening, _, body = stripped.partition("\n")
    language = opening[3:].strip().casefold()
    if language not in {"", "json"}:
        return stripped
    return body[:-3].strip()
