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
    def agent_checkpoint_db_path(self) -> Path:
        return self.data_dir / "agent_checkpoints.sqlite3"
