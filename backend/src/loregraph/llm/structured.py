from dataclasses import dataclass
from typing import Any, Protocol, cast, runtime_checkable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from loregraph.exceptions import GenerationError
from loregraph.llm.usage import LLMCallUsage, parse_usage

MAX_STRUCTURED_ATTEMPTS = 3


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
    ) -> None:
        self._model = model
        self._prompt_caching = prompt_caching
        self._max_attempts = max_attempts

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, cached_prefix: str = ""
    ) -> StructuredResult[T]:
        runnable = self._model.with_structured_output(schema, include_raw=True)
        messages: list[BaseMessage] = [
            SystemMessage(system),
            self._user_message(cached_prefix, user),
        ]
        usage = LLMCallUsage()
        last_error = "no response"
        for _ in range(self._max_attempts):
            raw_result = cast(dict[str, Any], await runnable.ainvoke(messages))
            raw_message = cast(AIMessage, raw_result["raw"])
            usage += parse_usage(raw_message.usage_metadata)
            parsed = raw_result.get("parsed")
            if parsed is not None:
                return StructuredResult(cast(T, parsed), usage)
            # Feed the concrete validation failure back and retry — never
            # continue silently with garbage (CLAUDE.md, "Валидация и
            # повторная генерация").
            last_error = str(raw_result.get("parsing_error"))
            messages = [
                *messages,
                raw_message,
                HumanMessage(
                    f"Your previous response failed schema validation: "
                    f"{last_error}. Respond again as a valid {schema.__name__}."
                ),
            ]
        raise GenerationError(
            f"LLM did not return a valid {schema.__name__} after "
            f"{self._max_attempts} attempts: {last_error}"
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
