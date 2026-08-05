"""AppComposition's defaults must be exactly what lifespan() built inline
before this seam existed — a private deployment overriding one field trusts
that every other field still behaves like the public app."""

from loregraph.composition import (
    AppComposition,
    default_engine,
    default_store_factories,
    default_vector_store,
)
from loregraph.config import Settings
from loregraph.storage.sqlite.attachment_store import SqliteAttachmentStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore


def test_defaults_are_the_public_sqlite_and_chroma_builders() -> None:
    composition = AppComposition()
    assert composition.build_engine is default_engine
    assert composition.build_store_factories is default_store_factories
    assert composition.build_vector_store is default_vector_store


def test_default_store_factories_maps_to_sqlite_implementations(
    settings: Settings,
) -> None:
    factories = default_store_factories(settings)
    assert factories.project is SqliteProjectStore
    assert factories.entity is SqliteEntityStore
    # attachment is a closure over settings.attachments_dir, not a bare class
    attachment_store = factories.attachment(None)  # type: ignore[arg-type]
    assert isinstance(attachment_store, SqliteAttachmentStore)


def test_default_vector_store_is_none_without_an_embedder(settings: Settings) -> None:
    assert default_vector_store(settings, None) is None
