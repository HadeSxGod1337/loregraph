"""Wire format for the settings page.

Field-shaped rather than section-shaped: the API reports a map of
`field name -> value + where it came from`, and the frontend renders the form
from the provider catalog. Adding a provider therefore changes one catalog
entry and nothing in this schema, in the router, or in the UI.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# Echoed back instead of a stored secret. A PUT that sends the mask back
# unchanged means "keep what's stored" — same convention connections use
# (schemas/connection.py), so the frontend has one rule, not two.
SECRET_MASK_PREFIX = "••••"

type SettingSourceOut = Literal["db", "env", "default"]


class SettingFieldOut(BaseModel):
    name: str
    # Masked for secrets, real value otherwise. None means "not set".
    value: Any = None
    source: SettingSourceOut
    secret: bool = False
    # For secrets, where `value` is only a mask: whether anything is stored.
    is_set: bool = True
    # Stored now, picked up by the next process start (tracing).
    restart_required: bool = False


class ProviderOut(BaseModel):
    id: str
    label: str
    api_key_field: str | None
    base_url_field: str | None
    console_url: str | None
    key_prefix_hint: str | None
    default_models: dict[str, str]
    suggested_models: list[str]
    supports_model_listing: bool


class EmbeddingProviderOut(BaseModel):
    id: str
    label: str
    model_field: str | None
    api_key_field: str | None
    base_url_field: str | None
    local: bool
    suggested_models: list[str]


class SettingsCatalogOut(BaseModel):
    """Everything the form needs to render itself, provider-agnostic."""

    providers: list[ProviderOut]
    embedding_providers: list[EmbeddingProviderOut]
    model_tiers: list[str]
    editable_fields: list[str]


class ReindexStatusOut(BaseModel):
    state: Literal["idle", "running", "done", "error"]
    total_projects: int = 0
    done_projects: int = 0
    current_project: str | None = None
    current_source: str | None = None
    total_sources: int = 0
    entities_indexed: int = 0
    sources_indexed: int = 0
    error: str | None = None
    model_id: str | None = None
    # Stored vectors were built by a configuration this process can't read
    # (embedding model or chunk layout changed since they were written), so
    # search finds nothing until a reindex runs. Detected at startup, not on
    # a setting change — the setting-change case already auto-reindexes.
    index_stale: bool = False


class LaunchOnlyOut(BaseModel):
    """Read-only mirror of the settings that are properties of how the process
    was started — shown so the page can explain why they aren't editable."""

    data_dir: str
    frontend_port: int
    play_mode_enabled: bool
    internet_mode_enabled: bool
    tls_enabled: bool
    trust_loopback: bool
    log_level: str


class AppSettingsOut(BaseModel):
    fields: dict[str, SettingFieldOut]
    llm_configured: bool
    embeddings_enabled: bool
    embedding_model_id: str | None
    reindex: ReindexStatusOut
    launch_only: LaunchOnlyOut


class AppSettingsUpdate(BaseModel):
    """Partial update. Only the named fields change; anything absent keeps its
    current layer (stored override, .env, or default)."""

    values: dict[str, Any] = Field(default_factory=dict)


class AppSettingsUpdateResult(BaseModel):
    settings: AppSettingsOut
    # Fields whose new value only applies after a restart (tracing).
    restart_required_fields: list[str] = Field(default_factory=list)
    # The embedding model changed, so stored vectors are stale.
    reindex_required: bool = False
    reindex_started: bool = False


class SettingsProbeRequest(BaseModel):
    """Test a candidate configuration without saving it. `values` is applied
    on top of the current settings for the duration of the probe only."""

    section: Literal["llm", "embeddings"] = "llm"
    values: dict[str, Any] = Field(default_factory=dict)


class SettingsProbeOut(BaseModel):
    ok: bool
    latency_ms: int
    error: str | None = None
    dimensions: int | None = None


class ProviderModelsOut(BaseModel):
    models: list[str]
    error: str | None = None
