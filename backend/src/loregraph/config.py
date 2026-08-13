from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

type LLMProvider = Literal[
    # Existing
    "anthropic",
    "openai",
    "ollama",
    # Tier 1 — dedicated LangChain packages
    "google",
    "mistral",
    "deepseek",
    "groq",
    "xai",
    "openrouter",
    # Tier 2 — dedicated packages
    "cohere",
    "together",
    "fireworks",
    "cerebras",
    # Tier 3 — OpenAI-compatible API
    "perplexity",
    "nebius",
]
type EmbeddingProviderKind = Literal[
    "local",
    "openai",
    "google",
    "mistral",
    "cohere",
    "together",
    "fireworks",
    "ollama",
    "disabled",
]
type TracingProviderKind = Literal["disabled", "langsmith", "langfuse"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CAMPAIGN_")

    data_dir: Path = Path("./data")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"
    # The public default trusts loopback as the DM (see api/security.py). Turn
    # this off when running behind a reverse proxy, where the peer address is
    # the proxy and loopback trust would let anyone in.
    trust_loopback: bool = True
    # LAN play mode: set by the launcher's --lan flag, not from the UI (the
    # bind address is a process-launch property). When on, /docs is disabled so
    # the API surface isn't mapped for anyone on the network. play_host is the
    # address to put in a player's invite link; play_frontend_port is where the
    # frontend is served.
    play_mode_enabled: bool = False
    # Internet mode (--internet): also ask the router, over UPnP, to forward
    # the port so players outside the local network can connect. Never on by
    # default — opening a port is the DM's decision, not a side effect.
    internet_mode_enabled: bool = False
    play_host: str | None = None
    # Where the app is reachable. In the packaged single-port setup the backend
    # serves the frontend too, so this is its own port; a dev setup running
    # Vite separately overrides it with 5173.
    play_frontend_port: int = 8000
    # Built frontend (npm run build). When present, the backend serves it, so
    # there is one process and one port to allow through a firewall or forward
    # on a router. Missing (a dev checkout that only ever ran `vite`) simply
    # means no SPA is served and the API still works.
    frontend_dist: Path = Path("../frontend/dist")
    # Optional TLS. Point both at a certificate and its private key and the app
    # serves HTTPS, and invite links become https:// — the same opt-in Foundry
    # offers. Without them everything stays plain HTTP, which is fine on your
    # own machine and on a home network, and is NOT fine over the internet:
    # a play token travels in the URL. A public certificate needs a domain;
    # a self-signed one works but every player gets a browser warning first.
    ssl_certfile: Path | None = None
    ssl_keyfile: Path | None = None

    # --- LLM (BYOK) ---
    llm_provider: LLMProvider = "anthropic"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    # Tier 1 — dedicated packages
    google_api_key: str | None = None
    mistral_api_key: str | None = None
    deepseek_api_key: str | None = None
    groq_api_key: str | None = None
    xai_api_key: str | None = None
    openrouter_api_key: str | None = None
    # Tier 2 — dedicated packages
    cohere_api_key: str | None = None
    together_api_key: str | None = None
    fireworks_api_key: str | None = None
    cerebras_api_key: str | None = None
    # Tier 3 — OpenAI-compatible
    perplexity_api_key: str | None = None
    perplexity_base_url: str = "https://api.perplexity.ai"
    nebius_api_key: str | None = None
    nebius_base_url: str = "https://api.staging.nebius.com/v1"
    # One model per task class, not one model for everything. Defaults are
    # Anthropic model ids; override all three when switching provider.
    # - assistant: the conversational loop (tool routing + concise replies +
    #   brief writing). A cheap, fast model is enough here and is the single
    #   largest recurring cost, so it gets its own tier defaulting to Haiku
    #   rather than sharing the pricier `generation` tier. Bump it to the
    #   generation model if routing/brief quality suffers.
    # - extraction: deterministic classification/verification (grounding judge).
    # - generation: creative lore batches (entities + relationship web).
    llm_model_assistant: str = "claude-haiku-4-5-20251001"
    llm_model_extraction: str = "claude-haiku-4-5-20251001"
    llm_model_generation: str = "claude-sonnet-5"

    # --- Agent ---
    # Hard per-run ceiling so a retry loop can't silently burn the user's key;
    # exceeding it interrupts into human_review, it does not kill the draft.
    agent_run_token_budget: int = 200_000
    web_search_enabled: bool = False
    # Anthropic prompt caching for the generate_lore stable prefix (existing
    # lore + knowledge base + instruction). Net positive when a proposal is
    # regenerated (title-collision retry, review revision, re-propose): those
    # reuse the cached prefix at ~0.1x. Only Anthropic supports it, and a
    # prefix below the model's cache minimum silently isn't cached (no write
    # penalty), so leaving this on is safe; turn off for a purely one-shot
    # workload to avoid the 1.25x cache-write premium on large first drafts.
    agent_prompt_caching: bool = True

    # --- Embeddings / vector store ---
    # "local" keeps lore on the machine (multilingual ONNX model via fastembed,
    # downloaded once on first use); API embeddings are an explicit opt-in
    # trade of privacy for quality. "disabled" turns vector indexing off
    # entirely (manual editor keeps working; agent retrieval degrades).
    embedding_provider: EmbeddingProviderKind = "local"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    openai_embedding_model: str = "text-embedding-3-small"
    google_embedding_model: str = "gemini-embedding-2-preview"
    mistral_embedding_model: str = "mistral-embed"
    cohere_embedding_model: str = "embed-english-light-v3.0"
    together_embedding_model: str = "intfloat/multilingual-e5-large-instruct"
    fireworks_embedding_model: str = "accounts/fireworks/models/fireworks-v1"
    ollama_embedding_model: str = "nomic-embed-text"

    # --- Tracing (optional) ---
    tracing_provider: TracingProviderKind = "disabled"
    langsmith_api_key: str | None = None
    langsmith_project: str = "loregraph"
    langsmith_endpoint: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "campaign.sqlite3"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def knowledge_dir(self) -> Path:
        return self.data_dir / "knowledge"

    @property
    def models_dir(self) -> Path:
        """Where the local embedding model is cached (~240 MB, downloaded once).

        Under data_dir like everything else the app owns. fastembed's own
        default is the system temp directory, which is wrong twice over: the
        user can neither find it nor connect it to this app, and Disk Cleanup
        (or a reboot, on some systems) silently deletes it — after which the
        app quietly re-downloads a quarter of a gigabyte.
        """
        return self.data_dir / "models"

    @property
    def agent_checkpoint_db_path(self) -> Path:
        return self.data_dir / "agent_checkpoints.sqlite3"

    @property
    def tls_enabled(self) -> bool:
        """TLS needs both halves; one alone is a misconfiguration, not a mode."""
        return self.ssl_certfile is not None and self.ssl_keyfile is not None

    @property
    def public_scheme(self) -> str:
        """Scheme for links handed to players (see api/routers/players.py)."""
        return "https" if self.tls_enabled else "http"

    @property
    def import_checkpoint_db_path(self) -> Path:
        # Separate file from agent_checkpoint_db_path: an import job is a
        # different kind of graph (ImportState, not AgentState) with its own
        # thread_id namespace — isolating the two files means a lock/
        # corruption issue in one never affects the other.
        return self.data_dir / "import_checkpoints.sqlite3"


# --- What the UI may change at runtime -----------------------------------
# Everything below describes Settings fields as *data*, so the settings API,
# the validator and the frontend form all read the same list instead of each
# keeping its own copy.

# Fields the settings API accepts. Deliberately a whitelist, not a blacklist:
# a stored override must never be able to reach data_dir, trust_loopback,
# ssl_*, play_* or cors_origins — those are launch/security properties, and a
# write to the app_settings table would otherwise be a privilege escalation.
LLM_SETTINGS_FIELDS: frozenset[str] = frozenset(
    {
        "llm_provider",
        "llm_model_assistant",
        "llm_model_extraction",
        "llm_model_generation",
        "agent_run_token_budget",
        "web_search_enabled",
        "agent_prompt_caching",
        "ollama_base_url",
        "perplexity_base_url",
        "nebius_base_url",
    }
)

# One key field per provider; also the fields that must be masked on the way
# out of the API and never logged.
API_KEY_SETTINGS_FIELDS: frozenset[str] = frozenset(
    {
        "anthropic_api_key",
        "openai_api_key",
        "google_api_key",
        "mistral_api_key",
        "deepseek_api_key",
        "groq_api_key",
        "xai_api_key",
        "openrouter_api_key",
        "cohere_api_key",
        "together_api_key",
        "fireworks_api_key",
        "cerebras_api_key",
        "perplexity_api_key",
        "nebius_api_key",
    }
)

EMBEDDING_SETTINGS_FIELDS: frozenset[str] = frozenset(
    {
        "embedding_provider",
        "embedding_model",
        "openai_embedding_model",
        "google_embedding_model",
        "mistral_embedding_model",
        "cohere_embedding_model",
        "together_embedding_model",
        "fireworks_embedding_model",
        "ollama_embedding_model",
    }
)

# Tracing is wired once at startup (see observability/), so a change here is
# stored and reported as pending rather than applied live.
TRACING_SETTINGS_FIELDS: frozenset[str] = frozenset(
    {
        "tracing_provider",
        "langsmith_api_key",
        "langsmith_project",
        "langsmith_endpoint",
        "langfuse_public_key",
        "langfuse_secret_key",
        "langfuse_host",
    }
)

SECRET_SETTINGS_FIELDS: frozenset[str] = API_KEY_SETTINGS_FIELDS | {
    "langsmith_api_key",
    "langfuse_public_key",
    "langfuse_secret_key",
}

UI_EDITABLE_FIELDS: frozenset[str] = (
    LLM_SETTINGS_FIELDS
    | API_KEY_SETTINGS_FIELDS
    | EMBEDDING_SETTINGS_FIELDS
    | TRACING_SETTINGS_FIELDS
)

# Changing any of these can change what embeddings come out, so the embedding
# stack is rebuilt (and, if the resulting model id differs, a reindex is
# required — embeddings from two models are not comparable). API keys and the
# Ollama URL are in here because an embedding provider can be built from them.
EMBEDDING_SENSITIVE_FIELDS: frozenset[str] = (
    EMBEDDING_SETTINGS_FIELDS | API_KEY_SETTINGS_FIELDS | {"ollama_base_url"}
)

# Stored, but only picked up by the next process start.
RESTART_REQUIRED_FIELDS: frozenset[str] = TRACING_SETTINGS_FIELDS
