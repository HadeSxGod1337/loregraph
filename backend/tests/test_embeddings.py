from importlib.metadata import version

from loregraph.llm.embeddings import FastEmbedProvider


def test_fast_embed_provider_model_id_includes_package_version() -> None:
    """model_id must change if the installed fastembed version changes, even
    when model_name doesn't — otherwise ChromaVectorStore's model-mismatch
    reindex trigger never fires for a fastembed upgrade that silently
    changes embedding behavior (see llm/embeddings.py's FastEmbedProvider
    docstring)."""
    provider = FastEmbedProvider("some/model-name")
    assert provider.model_id == f"some/model-name@fastembed-{version('fastembed')}"


def test_fast_embed_provider_model_id_is_computed_without_loading_the_model() -> None:
    # No TextEmbedding download/instantiation should happen just to read
    # model_id — construction stays cheap and offline-safe.
    provider = FastEmbedProvider("some/model-name")
    assert provider._model is None
    assert provider.model_id
