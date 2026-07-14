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
        case "google":
            return settings.google_api_key is not None
        case "mistral":
            return settings.mistral_api_key is not None
        case "deepseek":
            return settings.deepseek_api_key is not None
        case "groq":
            return settings.groq_api_key is not None
        case "xai":
            return settings.xai_api_key is not None
        case "openrouter":
            return settings.openrouter_api_key is not None
        case "cohere":
            return settings.cohere_api_key is not None
        case "together":
            return settings.together_api_key is not None
        case "fireworks":
            return settings.fireworks_api_key is not None
        case "cerebras":
            return settings.cerebras_api_key is not None
        case "perplexity":
            return settings.perplexity_api_key is not None
        case "nebius":
            return settings.nebius_api_key is not None
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
        # ── Existing providers ────────────────────────────────────────────
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
        # ── Tier 1 — dedicated LangChain packages ────────────────────────
        case "google":
            if settings.google_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'google' but CAMPAIGN_GOOGLE_API_KEY is not set"
                )
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=SecretStr(settings.google_api_key),
                temperature=temperature,
            )
        case "mistral":
            if settings.mistral_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'mistral' but CAMPAIGN_MISTRAL_API_KEY is not set"
                )
            from langchain_mistralai import ChatMistralAI

            return ChatMistralAI(
                model=model,
                api_key=SecretStr(settings.mistral_api_key),
                temperature=temperature,
            )
        case "deepseek":
            if settings.deepseek_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'deepseek' but"
                    " CAMPAIGN_DEEPSEEK_API_KEY is not set"
                )
            from langchain_deepseek import ChatDeepSeek

            return ChatDeepSeek(
                model=model,
                api_key=SecretStr(settings.deepseek_api_key),
                temperature=temperature,
            )
        case "groq":
            if settings.groq_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'groq' but CAMPAIGN_GROQ_API_KEY is not set"
                )
            from langchain_groq import ChatGroq

            return ChatGroq(
                model=model,
                api_key=SecretStr(settings.groq_api_key),
                temperature=temperature,
            )
        case "xai":
            if settings.xai_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'xai' but CAMPAIGN_XAI_API_KEY is not set"
                )
            from langchain_xai import ChatXAI

            return ChatXAI(
                model=model,
                api_key=SecretStr(settings.xai_api_key),
                temperature=temperature,
            )
        case "openrouter":
            if settings.openrouter_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'openrouter' but "
                    "CAMPAIGN_OPENROUTER_API_KEY is not set"
                )
            from langchain_openrouter import ChatOpenRouter

            return ChatOpenRouter(
                model=model,
                api_key=SecretStr(settings.openrouter_api_key),
                temperature=temperature,
            )
        # ── Tier 2 — dedicated packages ──────────────────────────────────
        case "cohere":
            if settings.cohere_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'cohere' but CAMPAIGN_COHERE_API_KEY is not set"
                )
            from langchain_cohere import ChatCohere

            return ChatCohere(
                model=model,
                api_key=SecretStr(settings.cohere_api_key),
                temperature=temperature,
            )
        case "together":
            if settings.together_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'together' but"
                    " CAMPAIGN_TOGETHER_API_KEY is not set"
                )
            from langchain_together import ChatTogether

            return ChatTogether(
                model=model,
                api_key=SecretStr(settings.together_api_key),
                temperature=temperature,
            )
        case "fireworks":
            if settings.fireworks_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'fireworks' but"
                    " CAMPAIGN_FIREWORKS_API_KEY is not set"
                )
            from langchain_fireworks import ChatFireworks

            return ChatFireworks(
                model=model,
                api_key=SecretStr(settings.fireworks_api_key),
                temperature=temperature,
            )
        case "cerebras":
            if settings.cerebras_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'cerebras' but"
                    " CAMPAIGN_CEREBRAS_API_KEY is not set"
                )
            from langchain_cerebras import ChatCerebras

            return ChatCerebras(
                model=model,
                api_key=SecretStr(settings.cerebras_api_key),
                temperature=temperature,
            )
        # ── Tier 3 — OpenAI-compatible API ───────────────────────────────
        case "perplexity":
            if settings.perplexity_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'perplexity' but "
                    "CAMPAIGN_PERPLEXITY_API_KEY is not set"
                )
            return ChatOpenAI(
                model=model,
                api_key=SecretStr(settings.perplexity_api_key),
                base_url=settings.perplexity_base_url,
                temperature=temperature,
            )
        case "nebius":
            if settings.nebius_api_key is None:
                raise ConfigurationError(
                    "llm_provider is 'nebius' but CAMPAIGN_NEBIUS_API_KEY is not set"
                )
            return ChatOpenAI(
                model=model,
                api_key=SecretStr(settings.nebius_api_key),
                base_url=settings.nebius_base_url,
                temperature=temperature,
            )
        case _:
            assert_never(settings.llm_provider)
