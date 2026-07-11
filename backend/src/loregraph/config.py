from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

type LLMProvider = Literal["anthropic", "openai", "ollama"]
type EmbeddingProviderKind = Literal["local", "openai", "disabled"]


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
    # One model per task class, not one model for everything (see CLAUDE.md,
    # "Модель и температура по типу задачи"). Defaults are Anthropic model ids;
    # override all three when switching provider.
    llm_model_extraction: str = "claude-haiku-4-5-20251001"
    llm_model_generation: str = "claude-sonnet-5"
    llm_model_composition: str = "claude-opus-4-8"

    # --- Agent ---
    # Hard per-run ceiling so a retry loop can't silently burn the user's key;
    # exceeding it interrupts into human_review, it does not kill the draft.
    agent_run_token_budget: int = 200_000
    web_search_enabled: bool = False

    # --- Embeddings / vector store ---
    # "local" keeps lore on the machine (multilingual ONNX model via fastembed,
    # downloaded once on first use); API embeddings are an explicit opt-in
    # trade of privacy for quality. "disabled" turns vector indexing off
    # entirely (manual editor keeps working; agent retrieval degrades).
    embedding_provider: EmbeddingProviderKind = "local"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    openai_embedding_model: str = "text-embedding-3-small"

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
    def agent_checkpoint_db_path(self) -> Path:
        return self.data_dir / "agent_checkpoints.sqlite3"
