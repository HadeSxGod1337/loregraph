"""Answering "does this configuration actually work?" before the user relies
on it — and listing the models a provider offers, where it offers a list.

Wrong key, model id that doesn't exist for this provider, Ollama not running:
all three otherwise surface much later, as a failed generation in the middle
of prep work. A probe is one tiny call made on demand from the settings page.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx
from langchain_core.messages import HumanMessage

from loregraph.config import API_KEY_SETTINGS_FIELDS, Settings
from loregraph.llm.catalog import PROVIDERS_BY_ID, provider_base_url
from loregraph.llm.embeddings import get_embedding_provider
from loregraph.llm.factory import ModelTier, get_chat_model

logger = logging.getLogger(__name__)

# A probe must be cheap and bounded: this is a liveness check, not a warmup.
PROBE_TIMEOUT_SECONDS = 30.0
MODEL_LIST_TIMEOUT_SECONDS = 10.0
# Enough to prove the key and the model id are accepted; the reply is discarded.
PROBE_PROMPT = "ping"
PROBE_ERROR_MAX_CHARS = 300


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    latency_ms: int
    # Provider-side error text, with any configured key redacted. None on success.
    error: str | None = None
    # Populated by the embedding probe: how many dimensions the model returns,
    # which is the thing that has to match across a whole collection.
    dimensions: int | None = None


def mask_keys(text: str, settings: Settings) -> str:
    """Redact every configured API key from provider error text.

    Provider SDKs are not careful about this — some echo the request, headers
    included — and this string goes into an HTTP response and a log line.
    """
    masked = text
    for field_name in API_KEY_SETTINGS_FIELDS:
        value = getattr(settings, field_name, None)
        if isinstance(value, str) and len(value) > 8:
            masked = masked.replace(value, f"••••{value[-4:]}")
    return masked


async def probe_chat_model(
    settings: Settings, tier: ModelTier = "assistant"
) -> ProbeResult:
    """One minimal completion against the configured provider/model."""
    started = time.perf_counter()
    try:
        model = get_chat_model(settings, tier=tier)
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            await model.ainvoke([HumanMessage(content=PROBE_PROMPT)])
    except TimeoutError:
        return ProbeResult(ok=False, latency_ms=_elapsed_ms(started), error="timeout")
    except Exception as e:  # every provider raises its own exception type
        return ProbeResult(
            ok=False,
            latency_ms=_elapsed_ms(started),
            error=mask_keys(str(e), settings)[:PROBE_ERROR_MAX_CHARS],
        )
    return ProbeResult(ok=True, latency_ms=_elapsed_ms(started))


async def probe_embeddings(settings: Settings) -> ProbeResult:
    """One minimal embedding call.

    Deliberately not on the chat probe's timeout: for the local provider this
    call is also the one-time model download (~240 MB), which legitimately
    takes minutes on a slow link."""
    started = time.perf_counter()
    try:
        embedder = get_embedding_provider(settings)
        if embedder is None:
            return ProbeResult(ok=True, latency_ms=0)
        vectors = await embedder.embed([PROBE_PROMPT])
    except Exception as e:  # provider-specific exception types
        return ProbeResult(
            ok=False,
            latency_ms=_elapsed_ms(started),
            error=mask_keys(str(e), settings)[:PROBE_ERROR_MAX_CHARS],
        )
    return ProbeResult(
        ok=True,
        latency_ms=_elapsed_ms(started),
        dimensions=len(vectors[0]) if vectors else None,
    )


@dataclass(frozen=True)
class ModelListing:
    models: tuple[str, ...]
    # Why the list is empty, when it is empty for a reason worth showing.
    error: str | None = None


async def list_provider_models(settings: Settings) -> ModelListing:
    """Models the configured provider currently offers.

    Generic on purpose: providers speak either the OpenAI `/models` shape, the
    Anthropic one or Ollama's `/api/tags`, so three small branches cover all
    fifteen — and a provider that publishes no list simply returns nothing,
    leaving the UI on its curated suggestions.
    """
    descriptor = PROVIDERS_BY_ID.get(settings.llm_provider)
    if descriptor is None or descriptor.models_style is None:
        return ModelListing(models=())
    if descriptor.models_style == "codex":
        if not settings.experimental_providers_enabled:
            return ModelListing(models=())
        try:
            from loregraph.llm.openai_codex_oauth import available_models

            names = await asyncio.to_thread(
                available_models, settings.openai_codex_oauth_path
            )
        except Exception as e:
            logger.debug("Codex model listing failed", exc_info=True)
            return ModelListing(
                models=(), error=mask_keys(str(e), settings)[:PROBE_ERROR_MAX_CHARS]
            )
        return ModelListing(models=tuple(names))

    base_url = provider_base_url(descriptor, settings)
    if base_url is None:
        return ModelListing(models=())
    api_key = (
        getattr(settings, descriptor.api_key_field, None)
        if descriptor.api_key_field
        else None
    )
    if descriptor.api_key_field is not None and not api_key:
        return ModelListing(models=(), error="no_api_key")

    try:
        async with httpx.AsyncClient(timeout=MODEL_LIST_TIMEOUT_SECONDS) as client:
            match descriptor.models_style:
                case "ollama":
                    response = await client.get(f"{base_url}/api/tags")
                    response.raise_for_status()
                    payload = response.json()
                    names = [
                        model["name"]
                        for model in payload.get("models", [])
                        if isinstance(model.get("name"), str)
                    ]
                case "anthropic":
                    response = await client.get(
                        f"{base_url}/models",
                        headers={
                            "x-api-key": str(api_key),
                            "anthropic-version": "2023-06-01",
                        },
                    )
                    response.raise_for_status()
                    names = _openai_style_ids(response.json())
                case _:
                    response = await client.get(
                        f"{base_url}/models",
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    response.raise_for_status()
                    names = _openai_style_ids(response.json())
    except httpx.HTTPError as e:
        logger.debug(
            "Model listing failed for %s", settings.llm_provider, exc_info=True
        )
        return ModelListing(
            models=(), error=mask_keys(str(e), settings)[:PROBE_ERROR_MAX_CHARS]
        )
    except (ValueError, KeyError, TypeError):
        # A 200 in a shape we don't recognize is not an outage — degrade to
        # the curated suggestions rather than showing the user a parse error.
        logger.debug("Unexpected model listing shape for %s", settings.llm_provider)
        return ModelListing(models=())
    return ModelListing(models=tuple(sorted(names)))


def _openai_style_ids(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [item["id"] for item in data if isinstance(item.get("id"), str)]


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
