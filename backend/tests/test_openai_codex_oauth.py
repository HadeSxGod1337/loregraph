import base64
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, SecretStr

from loregraph.llm import openai_codex_oauth
from loregraph.llm.structured import LangChainStructuredGenerator


def _jwt(claims: dict[str, Any]) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_request_headers_include_chatgpt_account_id() -> None:
    token = _jwt(
        {"https://api.openai.com/auth": {"chatgpt_account_id": "acct-test"}}
    )
    headers = openai_codex_oauth.request_headers(token)
    assert headers["ChatGPT-Account-ID"] == "acct-test"
    assert headers["originator"] == "codex_cli_rs"


def test_available_models_uses_live_visible_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _jwt(
        {"https://api.openai.com/auth": {"chatgpt_account_id": "acct-test"}}
    )
    monkeypatch.setattr(openai_codex_oauth, "access_token", lambda _: token)

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "models": [
                    {"slug": "second", "priority": 20},
                    {"slug": "hidden", "priority": 1, "visibility": "hidden"},
                    {"slug": "first", "priority": 10},
                ]
            }

    def fake_get(*args: Any, **kwargs: Any) -> Response:
        assert kwargs["headers"]["ChatGPT-Account-ID"] == "acct-test"
        return Response()

    monkeypatch.setattr("loregraph.llm.openai_codex_oauth.httpx.get", fake_get)
    assert openai_codex_oauth.available_models(tmp_path / "oauth.json") == [
        "first",
        "second",
    ]


def test_codex_client_moves_system_message_to_instructions() -> None:
    model = openai_codex_oauth.CodexChatOpenAI(
        model="gpt-5.3-codex",
        api_key=SecretStr("test"),
        base_url="https://chatgpt.com/backend-api/codex",
        use_responses_api=True,
        store=False,
    )
    payload = model._get_request_payload(
        [SystemMessage(content="Follow the lore rules."), HumanMessage(content="Hi")]
    )
    assert payload["instructions"] == "Follow the lore rules."
    assert all(
        not isinstance(item, dict)
        or item.get("role") not in {"system", "developer"}
        for item in payload["input"]
    )
    assert payload["input"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_codex_structured_output_uses_json_schema_dictionary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result(BaseModel):
        name: str

    captured: dict[str, Any] = {}

    def fake_with_structured_output(
        self: openai_codex_oauth.CodexChatOpenAI,
        schema: Any,
        **kwargs: Any,
    ) -> RunnableLambda[list[Any], dict[str, Any]]:
        captured["schema"] = schema

        async def invoke(messages: list[Any]) -> dict[str, Any]:
            return {
                "raw": AIMessage(
                    content="",
                    usage_metadata={
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                    },
                ),
                "parsed": {"name": "Iria"},
                "parsing_error": None,
            }

        return RunnableLambda(invoke)

    monkeypatch.setattr(
        openai_codex_oauth.CodexChatOpenAI,
        "with_structured_output",
        fake_with_structured_output,
    )
    model = openai_codex_oauth.CodexChatOpenAI(
        model="gpt-5.3-codex",
        api_key=SecretStr("test"),
        base_url="https://chatgpt.com/backend-api/codex",
        use_responses_api=True,
        store=False,
    )

    result = await LangChainStructuredGenerator(model).generate(
        Result, system="Return a name.", user="Create one."
    )

    assert captured["schema"] == Result.model_json_schema()
    assert result.value == Result(name="Iria")
