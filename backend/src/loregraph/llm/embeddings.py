import asyncio
import threading
from typing import Protocol, runtime_checkable

from fastembed import TextEmbedding
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from loregraph.config import Settings
from loregraph.exceptions import ConfigurationError


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns text into vectors. Implementations must be interchangeable, but
    their outputs are not: switching models requires a full reindex, so the
    model id is stored in collection metadata and checked on access."""

    @property
    def model_id(self) -> str: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedProvider:
    """Local ONNX embeddings (no API key, lore never leaves the machine).

    The model file is downloaded once on first use and cached; instantiation
    of the underlying TextEmbedding is deferred to first embed() so app
    startup stays instant and offline-safe.
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: TextEmbedding | None = None
        # Startup warmup and the first user request may race to initialize;
        # a plain threading lock (we run in to_thread) keeps it single-shot.
        self._init_lock = threading.Lock()

    @property
    def model_id(self) -> str:
        return self._model_name

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        with self._init_lock:
            if self._model is None:
                self._model = TextEmbedding(model_name=self._model_name)
        return [vector.tolist() for vector in self._model.embed(texts)]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # fastembed is synchronous CPU work — keep it off the event loop.
        return await asyncio.to_thread(self._embed_sync, texts)


class OpenAIEmbeddingProvider:
    """API embeddings — explicit opt-in trade of privacy for quality."""

    def __init__(self, model_name: str, api_key: str) -> None:
        self._model_name = model_name
        self._client = OpenAIEmbeddings(model=model_name, api_key=SecretStr(api_key))

    @property
    def model_id(self) -> str:
        return self._model_name

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._client.aembed_documents(texts)


class LangChainEmbeddingProvider:
    """Generic wrapper around any LangChain Embeddings class.

    Adapts the LangChain async interface to the project's EmbeddingProvider
    protocol so any LangChain-compatible provider can be used with zero
    additional code per provider.
    """

    def __init__(self, model_name: str, client: Embeddings) -> None:
        self._model_name = model_name
        self._client = client

    @property
    def model_id(self) -> str:
        return self._model_name

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._client.aembed_documents(texts)


def get_embedding_provider(settings: Settings) -> EmbeddingProvider | None:
    """Composition root for embeddings; None means vector indexing is off."""
    match settings.embedding_provider:
        case "local":
            return FastEmbedProvider(settings.embedding_model)
        case "openai":
            if settings.openai_api_key is None:
                raise ConfigurationError(
                    "embedding_provider is 'openai' but "
                    "CAMPAIGN_OPENAI_API_KEY is not set"
                )
            return OpenAIEmbeddingProvider(
                settings.openai_embedding_model, settings.openai_api_key
            )
        case "google":
            if settings.google_api_key is None:
                raise ConfigurationError(
                    "embedding_provider is 'google' but "
                    "CAMPAIGN_GOOGLE_API_KEY is not set"
                )
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            return LangChainEmbeddingProvider(
                settings.google_embedding_model,
                GoogleGenerativeAIEmbeddings(
                    model=settings.google_embedding_model,
                    google_api_key=SecretStr(settings.google_api_key),
                ),
            )
        case "mistral":
            if settings.mistral_api_key is None:
                raise ConfigurationError(
                    "embedding_provider is 'mistral' but "
                    "CAMPAIGN_MISTRAL_API_KEY is not set"
                )
            from langchain_mistralai import MistralAIEmbeddings

            return LangChainEmbeddingProvider(
                settings.mistral_embedding_model,
                MistralAIEmbeddings(
                    model=settings.mistral_embedding_model,
                    api_key=SecretStr(settings.mistral_api_key),
                ),
            )
        case "cohere":
            if settings.cohere_api_key is None:
                raise ConfigurationError(
                    "embedding_provider is 'cohere' but "
                    "CAMPAIGN_COHERE_API_KEY is not set"
                )
            from langchain_cohere import CohereEmbeddings

            return LangChainEmbeddingProvider(
                settings.cohere_embedding_model,
                CohereEmbeddings(
                    model=settings.cohere_embedding_model,
                    api_key=SecretStr(settings.cohere_api_key),
                ),
            )
        case "together":
            if settings.together_api_key is None:
                raise ConfigurationError(
                    "embedding_provider is 'together' but "
                    "CAMPAIGN_TOGETHER_API_KEY is not set"
                )
            from langchain_together import TogetherEmbeddings

            return LangChainEmbeddingProvider(
                settings.together_embedding_model,
                TogetherEmbeddings(
                    model=settings.together_embedding_model,
                    api_key=SecretStr(settings.together_api_key),
                ),
            )
        case "fireworks":
            if settings.fireworks_api_key is None:
                raise ConfigurationError(
                    "embedding_provider is 'fireworks' but "
                    "CAMPAIGN_FIREWORKS_API_KEY is not set"
                )
            from langchain_fireworks import FireworksEmbeddings

            return LangChainEmbeddingProvider(
                settings.fireworks_embedding_model,
                FireworksEmbeddings(
                    model=settings.fireworks_embedding_model,
                    api_key=SecretStr(settings.fireworks_api_key),
                ),
            )
        case "ollama":
            from langchain_ollama import OllamaEmbeddings

            return LangChainEmbeddingProvider(
                settings.ollama_embedding_model,
                OllamaEmbeddings(
                    model=settings.ollama_embedding_model,
                    base_url=settings.ollama_base_url,
                ),
            )
        case "disabled":
            return None
