from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

from loregraph.config import Settings
from loregraph.llm.embeddings import FastEmbedProvider, get_embedding_provider


def test_fast_embed_provider_model_id_includes_package_version() -> None:
    """model_id must change if the installed fastembed version changes, even
    when model_name doesn't — otherwise ChromaVectorStore's model-mismatch
    reindex trigger never fires for a fastembed upgrade that silently
    changes embedding behavior (see llm/embeddings.py's FastEmbedProvider
    docstring)."""
    provider = FastEmbedProvider("some/model-name", Path("./data/models"))
    assert provider.model_id == f"some/model-name@fastembed-{version('fastembed')}"


def test_fast_embed_provider_model_id_is_computed_without_loading_the_model() -> None:
    # No TextEmbedding download/instantiation should happen just to read
    # model_id — construction stays cheap and offline-safe.
    provider = FastEmbedProvider("some/model-name", Path("./data/models"))
    assert provider._model is None
    assert provider.model_id


def test_model_is_cached_under_the_app_data_dir(tmp_path: Path) -> None:
    """The 240 MB model must land in data_dir/models, not in fastembed's
    default (the system temp directory) — where the user can neither find it
    nor keep it: Disk Cleanup deletes it and the app silently re-downloads."""
    cache_dir = tmp_path / "models"
    provider = FastEmbedProvider("some/model-name", cache_dir)
    with patch("loregraph.llm.embeddings.TextEmbedding") as text_embedding:
        provider._embed_sync([])
    text_embedding.assert_called_once_with(
        model_name="some/model-name", cache_dir=str(cache_dir)
    )
    # Created eagerly: fastembed will not make a missing cache_dir itself.
    assert cache_dir.is_dir()


def test_local_provider_gets_the_cache_dir_from_settings(tmp_path: Path) -> None:
    settings = Settings(embedding_provider="local", data_dir=tmp_path)
    provider = get_embedding_provider(settings)
    assert isinstance(provider, FastEmbedProvider)
    assert provider._cache_dir == tmp_path / "models"
