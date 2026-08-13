"""Configuring the AI from the interface instead of by hand in `.env`.

Everything here works on the whole installation, not one project: which model
answers and which embedder indexes are properties of the app, and a campaign
that used a different model is not a different campaign.

Two rules shape this router:
* a secret never leaves it — values are masked on the way out, and a mask
  echoed back on the way in means "keep what's stored";
* an embedding change is applied only after the new provider can actually be
  built, so a typo in a key can't leave the app with no vector layer.
"""

import logging

from fastapi import APIRouter

from loregraph.api.deps import (
    AppSettingsStoreDep,
    EmbeddingStackDep,
    ReindexServiceDep,
    SettingsDep,
    SettingsProviderDep,
)
from loregraph.config import (
    EMBEDDING_SENSITIVE_FIELDS,
    RESTART_REQUIRED_FIELDS,
    SECRET_SETTINGS_FIELDS,
    UI_EDITABLE_FIELDS,
    Settings,
)
from loregraph.exceptions import ConfigurationError
from loregraph.llm.catalog import (
    EMBEDDING_PROVIDERS,
    PROVIDERS,
)
from loregraph.llm.factory import is_llm_configured
from loregraph.llm.probe import list_provider_models, probe_chat_model, probe_embeddings
from loregraph.schemas.app_settings import (
    SECRET_MASK_PREFIX,
    AppSettingsOut,
    AppSettingsUpdate,
    AppSettingsUpdateResult,
    EmbeddingProviderOut,
    LaunchOnlyOut,
    ProviderModelsOut,
    ProviderOut,
    ReindexStatusOut,
    SettingFieldOut,
    SettingsCatalogOut,
    SettingsProbeOut,
    SettingsProbeRequest,
)
from loregraph.services.embedding_stack import EmbeddingStack
from loregraph.services.reindex_job import ReindexProgress, ReindexService
from loregraph.services.settings_service import SettingsProvider, validate_override

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

MODEL_TIERS = ("assistant", "extraction", "generation")


def _mask(value: str) -> str:
    return SECRET_MASK_PREFIX + value[-4:] if len(value) > 4 else SECRET_MASK_PREFIX


def _field_out(name: str, provider: SettingsProvider) -> SettingFieldOut:
    raw = getattr(provider.current, name, None)
    secret = name in SECRET_SETTINGS_FIELDS
    is_set = raw is not None and raw != ""
    return SettingFieldOut(
        name=name,
        value=_mask(str(raw)) if secret and is_set else (None if secret else raw),
        source=provider.source_of(name),
        secret=secret,
        is_set=is_set,
        restart_required=name in RESTART_REQUIRED_FIELDS,
    )


def _launch_only(settings: Settings) -> LaunchOnlyOut:
    return LaunchOnlyOut(
        data_dir=str(settings.data_dir),
        frontend_port=settings.play_frontend_port,
        play_mode_enabled=settings.play_mode_enabled,
        internet_mode_enabled=settings.internet_mode_enabled,
        tls_enabled=settings.tls_enabled,
        trust_loopback=settings.trust_loopback,
        log_level=settings.log_level,
    )


def _reindex_out(
    progress: ReindexProgress, *, index_stale: bool = False
) -> ReindexStatusOut:
    return ReindexStatusOut(
        index_stale=index_stale,
        state=progress.state,
        total_projects=progress.total_projects,
        done_projects=progress.done_projects,
        current_project=progress.current_project,
        current_source=progress.current_source,
        total_sources=progress.total_sources,
        entities_indexed=progress.entities_indexed,
        sources_indexed=progress.sources_indexed,
        error=progress.error,
        model_id=progress.model_id,
    )


def _settings_out(
    provider: SettingsProvider, stack: EmbeddingStack, reindex: ReindexService
) -> AppSettingsOut:
    return AppSettingsOut(
        fields={
            name: _field_out(name, provider) for name in sorted(UI_EDITABLE_FIELDS)
        },
        llm_configured=is_llm_configured(provider.current),
        embeddings_enabled=stack.vector_index is not None,
        embedding_model_id=stack.model_id,
        reindex=_reindex_out(reindex.progress, index_stale=stack.index_stale),
        launch_only=_launch_only(provider.current),
    )


@router.get("", response_model=AppSettingsOut)
async def get_app_settings(
    provider: SettingsProviderDep,
    stack: EmbeddingStackDep,
    reindex: ReindexServiceDep,
) -> AppSettingsOut:
    return _settings_out(provider, stack, reindex)


@router.get("/catalog", response_model=SettingsCatalogOut)
async def get_catalog(settings: SettingsDep) -> SettingsCatalogOut:
    """Provider metadata (keys, defaults, suggestions) as data — the form is
    rendered from this, so no provider is hardcoded in the frontend."""
    return SettingsCatalogOut(
        providers=[
            ProviderOut(
                id=p.id,
                label=p.label,
                api_key_field=p.api_key_field,
                base_url_field=p.base_url_field,
                console_url=p.console_url,
                key_prefix_hint=p.key_prefix_hint,
                default_models=dict(p.default_models),
                suggested_models=list(p.suggested_models),
                supports_model_listing=p.models_style is not None,
            )
            for p in PROVIDERS
            if p.id != "openai_codex" or settings.experimental_providers_enabled
        ],
        embedding_providers=[
            EmbeddingProviderOut(
                id=p.id,
                label=p.label,
                model_field=p.model_field,
                api_key_field=p.api_key_field,
                base_url_field=p.base_url_field,
                local=p.local,
                suggested_models=list(p.suggested_models),
            )
            for p in EMBEDDING_PROVIDERS
        ],
        model_tiers=list(MODEL_TIERS),
        editable_fields=sorted(UI_EDITABLE_FIELDS),
    )


@router.get("/models", response_model=ProviderModelsOut)
async def get_provider_models(provider: SettingsProviderDep) -> ProviderModelsOut:
    """Models the configured provider currently offers, when it publishes a
    list. Empty is a normal answer, not an error — the UI falls back to the
    catalog's suggestions."""
    listing = await list_provider_models(provider.current)
    return ProviderModelsOut(models=list(listing.models), error=listing.error)


@router.put("", response_model=AppSettingsUpdateResult)
async def update_app_settings(
    data: AppSettingsUpdate,
    provider: SettingsProviderDep,
    store: AppSettingsStoreDep,
    stack: EmbeddingStackDep,
    reindex: ReindexServiceDep,
) -> AppSettingsUpdateResult:
    reindex_required = False
    async with provider.lock:
        incoming = _validated_patch(data.values)
        merged = {**provider.overrides, **incoming}
        candidate = provider.base.model_copy(update=merged)

        embedding_touched = any(name in EMBEDDING_SENSITIVE_FIELDS for name in incoming)
        # Build the new embedder BEFORE persisting anything: a provider that
        # can't be constructed (selected without its key) raises
        # ConfigurationError here, and the stored configuration is untouched.
        embedder = stack.build_embedder(candidate) if embedding_touched else None

        await store.set_many(incoming)
        provider.replace_overrides(merged)
        if embedding_touched:
            reindex_required = await stack.rebuild(provider.current, embedder)

    # Outside the lock: reindexing is a long background job, and holding the
    # settings lock for it would block every other settings read.
    reindex_started = _maybe_start_reindex(reindex, stack, reindex_required)
    return AppSettingsUpdateResult(
        settings=_settings_out(provider, stack, reindex),
        restart_required_fields=sorted(
            name for name in incoming if name in RESTART_REQUIRED_FIELDS
        ),
        reindex_required=reindex_required,
        reindex_started=reindex_started,
    )


@router.delete("/{field_name}", response_model=AppSettingsUpdateResult)
async def reset_app_setting(
    field_name: str,
    provider: SettingsProviderDep,
    store: AppSettingsStoreDep,
    stack: EmbeddingStackDep,
    reindex: ReindexServiceDep,
) -> AppSettingsUpdateResult:
    """Drop the stored override, so the field falls back to `.env` or its
    default — the only way back to what the launcher configured."""
    reindex_required = False
    async with provider.lock:
        # Validates the name against the whitelist; the value is irrelevant
        # here, so the field's current value is what gets re-checked.
        validate_override(field_name, getattr(provider.current, field_name, None))
        merged = {k: v for k, v in provider.overrides.items() if k != field_name}
        candidate = provider.base.model_copy(update=merged)
        embedding_touched = field_name in EMBEDDING_SENSITIVE_FIELDS
        embedder = stack.build_embedder(candidate) if embedding_touched else None

        await store.delete_keys([field_name])
        provider.replace_overrides(merged)
        if embedding_touched:
            reindex_required = await stack.rebuild(provider.current, embedder)

    reindex_started = _maybe_start_reindex(reindex, stack, reindex_required)
    return AppSettingsUpdateResult(
        settings=_settings_out(provider, stack, reindex),
        restart_required_fields=(
            [field_name] if field_name in RESTART_REQUIRED_FIELDS else []
        ),
        reindex_required=reindex_required,
        reindex_started=reindex_started,
    )


@router.post("/probe", response_model=SettingsProbeOut)
async def probe_settings(
    data: SettingsProbeRequest, provider: SettingsProviderDep
) -> SettingsProbeOut:
    """Try a candidate configuration without saving it — one tiny call, so a
    wrong key or a mistyped model id surfaces here and not mid-generation."""
    async with provider.lock:
        candidate = provider.current.model_copy(
            update=_validated_patch(data.values, keep_secrets_from=provider.current)
        )
    result = (
        await probe_embeddings(candidate)
        if data.section == "embeddings"
        else await probe_chat_model(candidate)
    )
    return SettingsProbeOut(
        ok=result.ok,
        latency_ms=result.latency_ms,
        error=result.error,
        dimensions=result.dimensions,
    )


@router.post("/reindex", response_model=ReindexStatusOut)
async def start_reindex(
    reindex: ReindexServiceDep, stack: EmbeddingStackDep
) -> ReindexStatusOut:
    """Rebuild every project's vector data with the current embedding model."""
    if stack.vector_index is None:
        raise ConfigurationError(
            "Vector indexing is disabled — set an embedding provider first"
        )
    return _reindex_out(reindex.start(), index_stale=stack.index_stale)


@router.get("/reindex", response_model=ReindexStatusOut)
async def reindex_status(
    reindex: ReindexServiceDep, stack: EmbeddingStackDep
) -> ReindexStatusOut:
    return _reindex_out(reindex.progress, index_stale=stack.index_stale)


def _validated_patch(
    values: dict[str, object], keep_secrets_from: Settings | None = None
) -> dict[str, object]:
    """Validate an incoming patch field by field.

    A masked secret echoed back means "unchanged": for a save it is dropped
    from the patch, for a probe it is replaced by the stored value, since the
    probe needs the real key to make a call.
    """
    patch: dict[str, object] = {}
    for name, value in values.items():
        if isinstance(value, str) and value.startswith(SECRET_MASK_PREFIX):
            if keep_secrets_from is not None:
                patch[name] = getattr(keep_secrets_from, name, None)
            continue
        # An emptied secret field means "no key", not an empty-string key.
        if name in SECRET_SETTINGS_FIELDS and value == "":
            value = None
        patch[name] = validate_override(name, value)
    return patch


def _maybe_start_reindex(
    reindex: ReindexService, stack: EmbeddingStack, reindex_required: bool
) -> bool:
    """Start the rebuild the moment it becomes necessary.

    Leaving it to the user would mean the assistant silently retrieves nothing
    until they happen to press a button they have no reason to look for.
    """
    if not reindex_required or stack.vector_index is None or reindex.is_running:
        return False
    reindex.start()
    return True
