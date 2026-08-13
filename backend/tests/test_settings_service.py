"""Layering rules for runtime settings: stored override > .env > default."""

from pathlib import Path
from typing import Any

import pytest

from loregraph.config import Settings
from loregraph.exceptions import SettingsFieldInvalidError, SettingsFieldUnknownError
from loregraph.services.settings_service import (
    SettingsProvider,
    sanitize_stored,
    validate_override,
)


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "data_dir": tmp_path,
        "embedding_provider": "disabled",
        "_env_file": None,
        **overrides,
    }
    return Settings(**kwargs)


def test_stored_override_wins_over_env(tmp_path: Path) -> None:
    base = make_settings(tmp_path, llm_model_generation="from-env")
    provider = SettingsProvider(base, {"llm_model_generation": "from-ui"})

    assert provider.current.llm_model_generation == "from-ui"
    assert provider.source_of("llm_model_generation") == "db"


def test_env_wins_over_default(tmp_path: Path) -> None:
    provider = SettingsProvider(
        make_settings(tmp_path, llm_model_generation="from-env")
    )

    assert provider.current.llm_model_generation == "from-env"
    assert provider.source_of("llm_model_generation") == "env"


def test_untouched_field_reports_default(tmp_path: Path) -> None:
    provider = SettingsProvider(make_settings(tmp_path))

    assert provider.source_of("llm_model_assistant") == "default"


def test_dropping_an_override_falls_back_to_env(tmp_path: Path) -> None:
    base = make_settings(tmp_path, llm_model_generation="from-env")
    provider = SettingsProvider(base, {"llm_model_generation": "from-ui"})

    provider.replace_overrides({})

    assert provider.current.llm_model_generation == "from-env"
    assert provider.source_of("llm_model_generation") == "env"


def test_base_settings_are_never_mutated(tmp_path: Path) -> None:
    base = make_settings(tmp_path)
    provider = SettingsProvider(base, {"llm_model_generation": "from-ui"})

    # The snapshot a request already holds must stay consistent even after a
    # later save replaces the current settings.
    snapshot = provider.current
    provider.replace_overrides({"llm_model_generation": "newer"})

    assert snapshot.llm_model_generation == "from-ui"
    assert base.llm_model_generation != "from-ui"


def test_non_editable_field_is_rejected() -> None:
    # Launch/security properties must not be reachable through settings.
    with pytest.raises(SettingsFieldUnknownError):
        validate_override("trust_loopback", False)
    with pytest.raises(SettingsFieldUnknownError):
        validate_override("data_dir", "/tmp/anywhere")


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(SettingsFieldInvalidError):
        validate_override("llm_provider", "not-a-provider")


def test_invalid_value_error_does_not_leak_the_value() -> None:
    with pytest.raises(SettingsFieldInvalidError) as excinfo:
        validate_override("agent_run_token_budget", "sk-ant-secret-looking-value")

    assert "sk-ant-secret-looking-value" not in str(excinfo.value)


def test_values_are_coerced_to_the_declared_type() -> None:
    assert validate_override("agent_run_token_budget", "5000") == 5000
    assert validate_override("web_search_enabled", True) is True


def test_sanitize_drops_junk_but_keeps_valid_rows() -> None:
    clean = sanitize_stored(
        {
            "llm_model_generation": "kept",
            "trust_loopback": False,  # not UI-editable
            "llm_provider": "nonsense",  # invalid value
        }
    )

    assert clean == {"llm_model_generation": "kept"}
