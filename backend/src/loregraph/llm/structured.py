from dataclasses import dataclass
from typing import Any, Protocol, cast, runtime_checkable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from loregraph.exceptions import GenerationError

MAX_STRUCTURED_ATTEMPTS = 3


@dataclass(frozen=True)
class StructuredResult[T]:
    value: T
    input_tokens: int
    output_tokens: int


@runtime_checkable
class StructuredGenerator(Protocol):
    """One structured LLM call with schema validation and usage accounting.

    A deliberate seam between agent nodes and LangChain: nodes are tested
    with fakes of this Protocol instead of fake chat models, and the
    retry-on-invalid-schema loop lives in exactly one place (DRY per
    CLAUDE.md: retries and schema validation are shared helpers)."""

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str
    ) -> StructuredResult[T]: ...


class LangChainStructuredGenerator:
    def __init__(
        self, model: BaseChatModel, max_attempts: int = MAX_STRUCTURED_ATTEMPTS
    ) -> None:
        self._model = model
        self._max_attempts = max_attempts

    async def generate[T: BaseModel](
        self, schema: type[T], *, system: str, user: str
    ) -> StructuredResult[T]:
        runnable = self._model.with_structured_output(schema, include_raw=True)
        messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(user)]
        input_tokens = output_tokens = 0
        last_error = "no response"
        for _ in range(self._max_attempts):
            raw_result = cast(dict[str, Any], await runnable.ainvoke(messages))
            raw_message = cast(AIMessage, raw_result["raw"])
            usage = cast(dict[str, int], raw_message.usage_metadata or {})
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            parsed = raw_result.get("parsed")
            if parsed is not None:
                return StructuredResult(cast(T, parsed), input_tokens, output_tokens)
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
