from collections import defaultdict
from typing import Any, cast

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from loregraph.exceptions import GenerationError
from loregraph.llm.capabilities import (
    ModelCapabilities,
    StructuredOutputStrategy,
    resolve_model_capabilities,
)
from loregraph.llm.structured import LangChainStructuredGenerator
from loregraph.schemas.import_job import WindowRegistryDraft


class NameResult(BaseModel):
    name: str


def _usage(input_tokens: int = 10, output_tokens: int = 2) -> dict[str, int]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _structured_response(
    parsed: BaseModel | None,
    *,
    error: str | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "raw": AIMessage("model response", usage_metadata=usage or _usage()),
        "parsed": parsed,
        "parsing_error": error,
    }


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        usage_metadata: dict[str, int] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.usage_metadata = usage_metadata


class ScriptedModel:
    """A tiny chat-model double that distinguishes structured mechanisms."""

    def __init__(
        self,
        *,
        native: list[object] | None = None,
        json_mode: list[object] | None = None,
        raw_json: list[object] | None = None,
    ) -> None:
        self._responses = {
            "native": list(native or []),
            "json_mode": list(json_mode or []),
            "raw_json": list(raw_json or []),
        }
        self.invocations: list[str] = []
        self.seen: defaultdict[str, list[list[BaseMessage]]] = defaultdict(list)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        strategy = "json_mode" if kwargs.get("method") == "json_mode" else "native"

        async def invoke(messages: list[BaseMessage]) -> object:
            return await self._next(strategy, messages)

        return RunnableLambda(invoke)

    async def ainvoke(self, messages: list[BaseMessage]) -> object:
        return await self._next("raw_json", messages)

    async def _next(self, strategy: str, messages: list[BaseMessage]) -> object:
        self.invocations.append(strategy)
        self.seen[strategy].append(messages)
        response = self._responses[strategy].pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _generator(
    model: ScriptedModel,
    *,
    capabilities: ModelCapabilities | None = None,
    provider: str = "test",
    model_name: str = "test-model",
    max_attempts: int = 3,
    max_transport_attempts: int = 2,
) -> LangChainStructuredGenerator:
    return LangChainStructuredGenerator(
        cast(BaseChatModel, model),
        capabilities=capabilities
        or ModelCapabilities(
            (
                StructuredOutputStrategy.NATIVE,
                StructuredOutputStrategy.JSON_MODE,
                StructuredOutputStrategy.RAW_JSON,
            )
        ),
        provider=provider,
        model_name=model_name,
        max_attempts=max_attempts,
        max_transport_attempts=max_transport_attempts,
        transport_retry_delay_seconds=0,
    )


@pytest.mark.asyncio
async def test_native_structured_output_returns_valid_result_in_one_request() -> None:
    model = ScriptedModel(native=[_structured_response(NameResult(name="Iria"))])

    result = await _generator(model).generate(NameResult, system="S", user="U")

    assert result.value == NameResult(name="Iria")
    assert model.invocations == ["native"]


@pytest.mark.asyncio
async def test_schema_validation_retries_without_switching_strategy() -> None:
    model = ScriptedModel(
        native=[
            _structured_response(
                None, error="name: Field required", usage=_usage(3, 1)
            ),
            _structured_response(NameResult(name="Iria"), usage=_usage(5, 2)),
        ]
    )

    result = await _generator(model).generate(NameResult, system="S", user="U")

    assert result.value.name == "Iria"
    assert model.invocations == ["native", "native"]
    assert "failed schema validation" in str(model.seen["native"][1][-1].content)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (8, 3)


@pytest.mark.asyncio
async def test_repeated_invalid_output_raises_controlled_generation_error() -> None:
    model = ScriptedModel(
        native=[
            _structured_response(None, error="name: Field required"),
            _structured_response(None, error="name: Field required"),
        ]
    )

    with pytest.raises(GenerationError, match="after 2 schema attempts"):
        await _generator(model, max_attempts=2).generate(
            NameResult, system="S", user="U"
        )

    assert model.invocations == ["native", "native"]


@pytest.mark.asyncio
async def test_deepseek_tool_choice_rejection_switches_once_to_json_mode() -> None:
    model = ScriptedModel(
        native=[
            ProviderError(
                "400 Thinking mode does not support this tool_choice",
                status_code=400,
                usage_metadata=_usage(3, 1),
            )
        ],
        json_mode=[_structured_response(NameResult(name="Iria"), usage=_usage(5, 2))],
    )

    result = await _generator(
        model, provider="deepseek", model_name="deepseek-chat"
    ).generate(NameResult, system="S", user="U")

    assert result.value.name == "Iria"
    assert model.invocations == ["native", "json_mode"]
    assert (result.usage.input_tokens, result.usage.output_tokens) == (8, 3)


@pytest.mark.asyncio
async def test_unsupported_json_schema_falls_back_to_json_mode() -> None:
    model = ScriptedModel(
        native=[
            ProviderError("response_format json_schema is unsupported", status_code=400)
        ],
        json_mode=[_structured_response(NameResult(name="Iria"))],
    )

    result = await _generator(model).generate(NameResult, system="S", user="U")

    assert result.value.name == "Iria"
    assert model.invocations == ["native", "json_mode"]


@pytest.mark.asyncio
async def test_transient_failure_retries_the_same_strategy() -> None:
    model = ScriptedModel(
        native=[
            ProviderError("rate limit", status_code=429, usage_metadata=_usage(3, 1)),
            _structured_response(NameResult(name="Iria"), usage=_usage(5, 2)),
        ]
    )

    result = await _generator(model).generate(NameResult, system="S", user="U")

    assert result.value.name == "Iria"
    assert model.invocations == ["native", "native"]
    assert (result.usage.input_tokens, result.usage.output_tokens) == (8, 3)


@pytest.mark.asyncio
async def test_permanent_auth_error_never_retries_or_downgrades() -> None:
    model = ScriptedModel(
        native=[ProviderError("invalid API key", status_code=401)],
        json_mode=[_structured_response(NameResult(name="must not run"))],
    )

    with pytest.raises(GenerationError, match="ProviderError"):
        await _generator(model).generate(NameResult, system="S", user="U")

    assert model.invocations == ["native"]


@pytest.mark.asyncio
async def test_raw_json_fallback_validates_and_counts_every_response() -> None:
    model = ScriptedModel(
        native=[ProviderError("does not support structured output", status_code=400)],
        json_mode=[ProviderError("response_format unsupported", status_code=400)],
        raw_json=[
            AIMessage('{"wrong": true}', usage_metadata=_usage(4, 1)),
            AIMessage('```json\n{"name": "Iria"}\n```', usage_metadata=_usage(6, 2)),
        ],
    )

    result = await _generator(model).generate(NameResult, system="S", user="U")

    assert result.value.name == "Iria"
    assert model.invocations == ["native", "json_mode", "raw_json", "raw_json"]
    assert (result.usage.input_tokens, result.usage.output_tokens) == (10, 3)


def test_deepseek_reasoner_uses_raw_json_without_forced_tool_choice() -> None:
    capabilities = resolve_model_capabilities("deepseek", "deepseek-reasoner")

    assert capabilities.structured_output_strategies == (
        StructuredOutputStrategy.RAW_JSON,
    )


@pytest.mark.asyncio
async def test_import_shaped_schema_can_use_generic_raw_json_fallback() -> None:
    model = ScriptedModel(
        raw_json=[
            AIMessage(
                '{"entries": ['
                '{"canonical_name": "Iria", "aliases": [], "type": "npc"}'
                "]}"
            )
        ]
    )
    generator = _generator(
        model,
        capabilities=ModelCapabilities((StructuredOutputStrategy.RAW_JSON,)),
        provider="deepseek",
        model_name="deepseek-reasoner",
    )

    result = await generator.generate(WindowRegistryDraft, system="S", user="U")

    assert result.value.entries[0].canonical_name == "Iria"
    assert model.invocations == ["raw_json"]
