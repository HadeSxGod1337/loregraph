import base64
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import SecretStr

from loregraph.llm import openai_codex_oauth


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
