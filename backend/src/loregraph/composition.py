"""Public composition root: which concrete class backs each piece of
infrastructure `lifespan()` builds. Every `build_*` default here reproduces
today's hardcoded sqlite/chroma wiring exactly — a private deployment
overrides only the fields it needs (e.g. swap storage for Postgres) via its
own `AppComposition(...)` instance, inheriting every other default unchanged.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from loregraph.config import Settings
from loregraph.llm.embeddings import EmbeddingProvider
from loregraph.storage.composition import StoreFactories
from loregraph.storage.sqlite.agent_session_store import SqliteAgentSessionStore
from loregraph.storage.sqlite.attachment_store import SqliteAttachmentStore
from loregraph.storage.sqlite.connection_store import (
    SqliteConnectionEntityLinkStore,
    SqliteConnectionStore,
)
from loregraph.storage.sqlite.db import create_engine_for
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.entity_template_store import SqliteEntityTemplateStore
from loregraph.storage.sqlite.import_job_store import SqliteImportJobStore
from loregraph.storage.sqlite.knowledge_source_store import SqliteKnowledgeSourceStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from loregraph.storage.sqlite.sheet_preset_store import SqliteSheetPresetStore
from loregraph.storage.sqlite.usage_store import SqliteUsageStore
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore
from loregraph.storage.vectorstore.protocols import VectorStore


def default_engine(settings: Settings) -> AsyncEngine:
    return create_engine_for(settings.db_path)


def default_store_factories(settings: Settings) -> StoreFactories:
    return StoreFactories(
        project=SqliteProjectStore,
        entity=SqliteEntityStore,
        entity_template=SqliteEntityTemplateStore,
        sheet_preset=SqliteSheetPresetStore,
        edge=SqliteEdgeStore,
        attachment=lambda session: SqliteAttachmentStore(
            session, settings.attachments_dir
        ),
        agent_session=SqliteAgentSessionStore,
        import_job=SqliteImportJobStore,
        knowledge_source=lambda session: SqliteKnowledgeSourceStore(
            session, settings.knowledge_dir
        ),
        usage=SqliteUsageStore,
        connection=SqliteConnectionStore,
        connection_entity_link=SqliteConnectionEntityLinkStore,
    )


def default_vector_store(
    settings: Settings, embedder: EmbeddingProvider | None
) -> VectorStore | None:
    if embedder is None:
        return None
    return ChromaVectorStore(settings.chroma_dir, embedder)


@dataclass(frozen=True)
class AppComposition:
    """Public defaults — sqlite + chroma, exactly what `lifespan()` built
    inline before this seam existed. A private deployment overrides only
    the fields it needs; every other field keeps working through the public
    default with zero changes to public code."""

    build_engine: Callable[[Settings], AsyncEngine] = default_engine
    build_store_factories: Callable[[Settings], StoreFactories] = (
        default_store_factories
    )
    build_vector_store: Callable[
        [Settings, EmbeddingProvider | None], VectorStore | None
    ] = default_vector_store
