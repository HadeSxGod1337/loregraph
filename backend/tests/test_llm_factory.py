from pathlib import Path
from typing import Any

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from loregraph.config import Settings
from loregraph.exceptions import ConfigurationError
from loregraph.llm.factory import TIER_TEMPERATURE, ModelTier, get_chat_model
from loregraph.llm.openai_codex_oauth import CodexChatOpenAI


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    # _env_file=None keeps the developer's real .env out of the tests. mypy
    # doesn't see pydantic-settings' dynamic init kwargs, hence the dict pass.
    return Settings(**{"data_dir": tmp_path, "_env_file": None, **overrides})


def test_anthropic_provider(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, llm_provider="anthropic", anthropic_api_key="sk-ant-test"
    )
    model = get_chat_model(settings, tier="generation")
    assert isinstance(model, ChatAnthropic)
    assert model.model == settings.llm_model_generation


def test_openai_provider(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        llm_provider="openai",
        openai_api_key="sk-test",
        llm_model_generation="gpt-test",
    )
    model = get_chat_model(settings, tier="generation")
    assert isinstance(model, ChatOpenAI)
    assert type(model) is ChatOpenAI
    assert model.model_name == "gpt-test"


def test_ollama_provider_needs_no_key(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, llm_provider="ollama", llm_model_generation="llama-test"
    )
    model = get_chat_model(settings, tier="generation")
    assert isinstance(model, ChatOllama)
    assert model.model == "llama-test"
    assert model.base_url == settings.ollama_base_url


def test_openai_codex_requires_a_completed_oauth_login(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, llm_provider="openai_codex", experimental_providers_enabled=True
    )
    with pytest.raises(ConfigurationError, match="OAuth is not connected"):
        get_chat_model(settings, tier="generation")


def test_openai_codex_provider_uses_responses_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("loregraph.llm.factory.codex_access_token", lambda _: "token")
    settings = make_settings(
        tmp_path,
        llm_provider="openai_codex",
        experimental_providers_enabled=True,
        llm_model_generation="gpt-5-codex",
    )
    model = get_chat_model(settings, tier="generation")
    assert isinstance(model, CodexChatOpenAI)
    assert model.use_responses_api is True
    assert model.store is False
    assert str(model.openai_api_base) == settings.openai_codex_base_url
    assert model.default_headers is not None
    assert model.default_headers["originator"] == "codex_cli_rs"


def test_openai_codex_requires_explicit_experimental_opt_in(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, llm_provider="openai_codex")
    with pytest.raises(ConfigurationError, match="experimental"):
        get_chat_model(settings, tier="generation")


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_missing_api_key_raises_configuration_error(
    tmp_path: Path, provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CAMPAIGN_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CAMPAIGN_OPENAI_API_KEY", raising=False)
    settings = make_settings(tmp_path, llm_provider=provider)
    with pytest.raises(ConfigurationError):
        get_chat_model(settings, tier="generation")


@pytest.mark.parametrize(
    "tier,expected_model_field",
    [
        ("assistant", "llm_model_assistant"),
        ("extraction", "llm_model_extraction"),
        ("generation", "llm_model_generation"),
    ],
)
def test_tier_selects_model_and_temperature(
    tmp_path: Path, tier: ModelTier, expected_model_field: str
) -> None:
    settings = make_settings(
        tmp_path, llm_provider="anthropic", anthropic_api_key="sk-ant-test"
    )
    model = get_chat_model(settings, tier=tier)
    assert isinstance(model, ChatAnthropic)
    assert model.model == getattr(settings, expected_model_field)
    assert model.temperature == TIER_TEMPERATURE[tier]


def test_api_key_is_not_exposed_in_error_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CAMPAIGN_ANTHROPIC_API_KEY", raising=False)
    settings = make_settings(tmp_path, llm_provider="anthropic")
    with pytest.raises(ConfigurationError) as exc_info:
        get_chat_model(settings, tier="extraction")
    # The message names the env var to set, never a key value.
    assert "CAMPAIGN_ANTHROPIC_API_KEY" in str(exc_info.value)
