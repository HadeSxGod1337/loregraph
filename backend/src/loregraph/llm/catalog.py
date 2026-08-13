"""What each provider needs, as data — the single source the settings API,
the first-run launcher wizard and the frontend form all read.

Before this file the same table (which key field, which default models, which
console hands out keys) was duplicated in `scripts/start.ps1`'s wizard and in
the developer's head. Adding a provider means adding one entry here plus its
branch in `llm/factory.py`; nothing in the API or the UI is per-provider code.
"""

from dataclasses import dataclass, field

from loregraph.config import EmbeddingProviderKind, LLMProvider, Settings

type ModelTier = str  # llm.factory.ModelTier; kept loose to avoid a cycle


@dataclass(frozen=True)
class ProviderDescriptor:
    """One chat-LLM provider, described for configuration purposes."""

    id: LLMProvider
    label: str
    # Settings field holding this provider's key; None = no key at all (a
    # locally hosted runtime), which is also what "needs no configuration"
    # means to `is_llm_configured`.
    api_key_field: str | None
    # Settings field holding an overridable base URL, when the provider has one.
    base_url_field: str | None = None
    # Where the user gets a key. Shown as a link next to the empty key field.
    console_url: str | None = None
    key_prefix_hint: str | None = None
    # Sensible starting point per tier — the same values the launcher wizard
    # wrote into .env, now defined once.
    default_models: dict[str, str] = field(default_factory=dict)
    # Non-exhaustive: the model field stays free text, these are only the
    # datalist suggestions for people who don't know the provider's ids.
    suggested_models: tuple[str, ...] = ()
    # Live listing. `api_base` + "/models" for OpenAI-compatible APIs; Ollama
    # has its own shape. None = this provider publishes no list, and the UI
    # silently falls back to `suggested_models`.
    api_base: str | None = None
    models_style: str | None = None  # "openai" | "ollama" | None


_ANTHROPIC_MODELS = (
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
)

PROVIDERS: tuple[ProviderDescriptor, ...] = (
    ProviderDescriptor(
        id="anthropic",
        label="Anthropic (Claude)",
        api_key_field="anthropic_api_key",
        console_url="https://console.anthropic.com/settings/keys",
        key_prefix_hint="sk-ant-",
        default_models={
            "assistant": "claude-haiku-4-5-20251001",
            "extraction": "claude-haiku-4-5-20251001",
            "generation": "claude-sonnet-5",
        },
        suggested_models=_ANTHROPIC_MODELS,
        api_base="https://api.anthropic.com/v1",
        models_style="anthropic",
    ),
    ProviderDescriptor(
        id="openai",
        label="OpenAI",
        api_key_field="openai_api_key",
        console_url="https://platform.openai.com/api-keys",
        key_prefix_hint="sk-",
        default_models={
            "assistant": "gpt-4o-mini",
            "extraction": "gpt-4o-mini",
            "generation": "gpt-4o",
        },
        suggested_models=("gpt-4o", "gpt-4o-mini", "o3-mini"),
        api_base="https://api.openai.com/v1",
        models_style="openai",
    ),
    ProviderDescriptor(
        id="ollama",
        label="Ollama (local)",
        api_key_field=None,
        base_url_field="ollama_base_url",
        console_url="https://ollama.com/library",
        default_models={
            "assistant": "llama3.3",
            "extraction": "llama3.3",
            "generation": "llama3.3",
        },
        suggested_models=("llama3.3", "qwen2.5", "mistral-nemo"),
        models_style="ollama",
    ),
    ProviderDescriptor(
        id="google",
        label="Google Gemini",
        api_key_field="google_api_key",
        console_url="https://aistudio.google.com/apikey",
        key_prefix_hint="AIza",
        default_models={
            "assistant": "gemini-2.0-flash",
            "extraction": "gemini-2.0-flash",
            "generation": "gemini-2.5-pro-preview-05-06",
        },
        suggested_models=("gemini-2.0-flash", "gemini-2.5-pro-preview-05-06"),
    ),
    ProviderDescriptor(
        id="mistral",
        label="Mistral",
        api_key_field="mistral_api_key",
        console_url="https://console.mistral.ai/api-keys",
        default_models={
            "assistant": "mistral-small-latest",
            "extraction": "mistral-small-latest",
            "generation": "mistral-large-latest",
        },
        suggested_models=("mistral-small-latest", "mistral-large-latest"),
        api_base="https://api.mistral.ai/v1",
        models_style="openai",
    ),
    ProviderDescriptor(
        id="deepseek",
        label="DeepSeek",
        api_key_field="deepseek_api_key",
        console_url="https://platform.deepseek.com/api_keys",
        key_prefix_hint="sk-",
        default_models={
            "assistant": "deepseek-chat",
            "extraction": "deepseek-chat",
            "generation": "deepseek-reasoner",
        },
        suggested_models=("deepseek-chat", "deepseek-reasoner"),
        api_base="https://api.deepseek.com",
        models_style="openai",
    ),
    ProviderDescriptor(
        id="groq",
        label="Groq",
        api_key_field="groq_api_key",
        console_url="https://console.groq.com/keys",
        key_prefix_hint="gsk_",
        default_models={
            "assistant": "llama-3.3-70b-versatile",
            "extraction": "llama-3.3-70b-versatile",
            "generation": "llama-3.3-70b-versatile",
        },
        suggested_models=("llama-3.3-70b-versatile",),
        api_base="https://api.groq.com/openai/v1",
        models_style="openai",
    ),
    ProviderDescriptor(
        id="xai",
        label="xAI (Grok)",
        api_key_field="xai_api_key",
        console_url="https://console.x.ai",
        key_prefix_hint="xai-",
        default_models={
            "assistant": "grok-3-mini",
            "extraction": "grok-3-mini",
            "generation": "grok-3",
        },
        suggested_models=("grok-3", "grok-3-mini"),
        api_base="https://api.x.ai/v1",
        models_style="openai",
    ),
    ProviderDescriptor(
        id="openrouter",
        label="OpenRouter",
        api_key_field="openrouter_api_key",
        console_url="https://openrouter.ai/keys",
        key_prefix_hint="sk-or-",
        default_models={
            "assistant": "anthropic/claude-3.5-haiku",
            "extraction": "anthropic/claude-3.5-haiku",
            "generation": "anthropic/claude-sonnet-4",
        },
        suggested_models=(
            "anthropic/claude-sonnet-4",
            "anthropic/claude-3.5-haiku",
            "openai/gpt-4o",
        ),
        api_base="https://openrouter.ai/api/v1",
        models_style="openai",
    ),
    ProviderDescriptor(
        id="cohere",
        label="Cohere",
        api_key_field="cohere_api_key",
        console_url="https://dashboard.cohere.com/api-keys",
        default_models={
            "assistant": "command-r-plus",
            "extraction": "command-r",
            "generation": "command-r-plus",
        },
        suggested_models=("command-r", "command-r-plus"),
    ),
    ProviderDescriptor(
        id="together",
        label="Together AI",
        api_key_field="together_api_key",
        console_url="https://api.together.ai/settings/api-keys",
        default_models={
            "assistant": "meta-llama/Llama-3-70b-chat-hf",
            "extraction": "meta-llama/Llama-3-8b-chat-hf",
            "generation": "meta-llama/Llama-3-70b-chat-hf",
        },
        suggested_models=(
            "meta-llama/Llama-3-70b-chat-hf",
            "meta-llama/Llama-3-8b-chat-hf",
        ),
        api_base="https://api.together.xyz/v1",
        models_style="openai",
    ),
    ProviderDescriptor(
        id="fireworks",
        label="Fireworks AI",
        api_key_field="fireworks_api_key",
        console_url="https://fireworks.ai/account/api-keys",
        default_models={
            "assistant": "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "extraction": "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "generation": "accounts/fireworks/models/llama-v3p3-70b-instruct",
        },
        suggested_models=("accounts/fireworks/models/llama-v3p3-70b-instruct",),
        api_base="https://api.fireworks.ai/inference/v1",
        models_style="openai",
    ),
    ProviderDescriptor(
        id="cerebras",
        label="Cerebras",
        api_key_field="cerebras_api_key",
        console_url="https://cloud.cerebras.ai",
        default_models={
            "assistant": "llama-3.3-70b",
            "extraction": "llama-3.3-70b",
            "generation": "llama-3.3-70b",
        },
        suggested_models=("llama-3.3-70b",),
        api_base="https://api.cerebras.ai/v1",
        models_style="openai",
    ),
    ProviderDescriptor(
        id="perplexity",
        label="Perplexity",
        api_key_field="perplexity_api_key",
        base_url_field="perplexity_base_url",
        console_url="https://www.perplexity.ai/settings/api",
        key_prefix_hint="pplx-",
        default_models={
            "assistant": "sonar",
            "extraction": "sonar",
            "generation": "sonar-pro",
        },
        suggested_models=("sonar", "sonar-pro"),
    ),
    ProviderDescriptor(
        id="nebius",
        label="Nebius",
        api_key_field="nebius_api_key",
        base_url_field="nebius_base_url",
        console_url="https://studio.nebius.ai",
        default_models={
            "assistant": "meta-llama/Llama-3-70B-Instruct",
            "extraction": "meta-llama/Llama-3-8B-Instruct",
            "generation": "meta-llama/Llama-3-70B-Instruct",
        },
        suggested_models=(
            "meta-llama/Llama-3-70B-Instruct",
            "meta-llama/Llama-3-8B-Instruct",
        ),
        models_style="openai",
    ),
)

PROVIDERS_BY_ID: dict[str, ProviderDescriptor] = {p.id: p for p in PROVIDERS}


@dataclass(frozen=True)
class EmbeddingProviderDescriptor:
    """One embedding provider. `model_field` is what the UI edits when this
    provider is selected — each provider keeps its own model setting so
    switching back and forth doesn't lose the other one's model name."""

    id: EmbeddingProviderKind
    label: str
    model_field: str | None
    api_key_field: str | None = None
    base_url_field: str | None = None
    # Runs on this machine: no key, and the campaign text never leaves it.
    local: bool = False
    suggested_models: tuple[str, ...] = ()


EMBEDDING_PROVIDERS: tuple[EmbeddingProviderDescriptor, ...] = (
    EmbeddingProviderDescriptor(
        id="local",
        label="Local model (fastembed)",
        model_field="embedding_model",
        local=True,
        suggested_models=(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "BAAI/bge-small-en-v1.5",
            "intfloat/multilingual-e5-large",
        ),
    ),
    EmbeddingProviderDescriptor(
        id="openai",
        label="OpenAI",
        model_field="openai_embedding_model",
        api_key_field="openai_api_key",
        suggested_models=("text-embedding-3-small", "text-embedding-3-large"),
    ),
    EmbeddingProviderDescriptor(
        id="google",
        label="Google Gemini",
        model_field="google_embedding_model",
        api_key_field="google_api_key",
        suggested_models=("gemini-embedding-2-preview",),
    ),
    EmbeddingProviderDescriptor(
        id="mistral",
        label="Mistral",
        model_field="mistral_embedding_model",
        api_key_field="mistral_api_key",
        suggested_models=("mistral-embed",),
    ),
    EmbeddingProviderDescriptor(
        id="cohere",
        label="Cohere",
        model_field="cohere_embedding_model",
        api_key_field="cohere_api_key",
        suggested_models=("embed-english-light-v3.0", "embed-multilingual-v3.0"),
    ),
    EmbeddingProviderDescriptor(
        id="together",
        label="Together AI",
        model_field="together_embedding_model",
        api_key_field="together_api_key",
        suggested_models=("intfloat/multilingual-e5-large-instruct",),
    ),
    EmbeddingProviderDescriptor(
        id="fireworks",
        label="Fireworks AI",
        model_field="fireworks_embedding_model",
        api_key_field="fireworks_api_key",
        suggested_models=("accounts/fireworks/models/fireworks-v1",),
    ),
    EmbeddingProviderDescriptor(
        id="ollama",
        label="Ollama (local)",
        model_field="ollama_embedding_model",
        base_url_field="ollama_base_url",
        local=True,
        suggested_models=("nomic-embed-text", "mxbai-embed-large"),
    ),
    EmbeddingProviderDescriptor(
        id="disabled",
        label="Disabled (no vector search)",
        model_field=None,
    ),
)

EMBEDDING_PROVIDERS_BY_ID: dict[str, EmbeddingProviderDescriptor] = {
    p.id: p for p in EMBEDDING_PROVIDERS
}


def provider_base_url(descriptor: ProviderDescriptor, settings: Settings) -> str | None:
    """Effective API base for this provider — the user's override when the
    provider exposes one, otherwise the built-in default."""
    if descriptor.base_url_field is not None:
        configured = getattr(settings, descriptor.base_url_field, None)
        if isinstance(configured, str) and configured:
            return configured.rstrip("/")
    return descriptor.api_base.rstrip("/") if descriptor.api_base else None
