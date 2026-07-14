from typing import Literal, assert_never

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from loregraph.config import Settings
from loregraph.exceptions import ConfigurationError

type ModelTier = Literal["assistant", "extraction", "generation"]

# Temperature per task class:
# assistant is tool-routing + concise grounded chat (low temp for reliable
# routing, still natural), extraction is deterministic classification,
# generation is creative content.
TIER_TEMPERATURE: dict[ModelTier, float] = {
    "assistant": 0.3,
    "extraction": 0.0,
    "generation": 0.8,
}


def _model_for_tier(settings: Settings, tier: ModelTier) -> str:
    match tier:
        case "assistant":
            return settings.llm_model_assistant
        case "extraction":
            return settings.llm_model_extraction
        case "generation":
            return settings.llm_model_generation
        case _:
            assert_never(tier)


def is_llm_configured(settings: Settings) -> bool:
    """Whether get_chat_model would succeed — for UI onboarding, not errors."""
    match settings.llm_provider:
        case "anthropic":
            return settings.anthropic_api_key is not None
        case "openai":
            return settings.openai_api_key is not None
        case "ollama":
            return True
        case _:
            assert_never(settings.llm_provider)


def get_chat_model(settings: Settings, *, tier: ModelTier) -> BaseChatModel:
    """Composition root for LLM providers.

    The only place in the codebase that knows which concrete chat model class
    is behind the `BaseChatModel` abstraction; agent nodes receive the result
    via DI and stay provider-agnostic.
    """
    model = _model_for_tier(settings, tier)
    temperature = TIER_TEMPERATURE[tier]
    match settings.llm_provider:
        case "anthropic":
            if settings.anthropic_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'anthropic' but "
                    "CAMPAIGN_ANTHROPIC_API_KEY is not set"
                )
            return ChatAnthropic(
                model_name=model,
                api_key=SecretStr(settings.anthropic_api_key),
                temperature=temperature,
                timeout=None,
                stop=None,
            )
        case "openai":
            if settings.openai_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'openai' but CAMPAIGN_OPENAI_API_KEY is not set"
                )
            return ChatOpenAI(
                model=model,
                api_key=SecretStr(settings.openai_api_key),
                temperature=temperature,
            )
        case "ollama":
            return ChatOllama(
                model=model,
                base_url=settings.ollama_base_url,
                temperature=temperature,
            )
        case _:
            assert_never(settings.llm_provider)
