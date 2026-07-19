import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from loregraph.api.routers import (
    agent,
    attachments,
    connections,
    edges,
    entities,
    graph,
    knowledge,
    projects,
    realtime,
    usage,
)
from loregraph.config import Settings
from loregraph.connectors.runtime import ConnectorRuntime
from loregraph.connectors.setup import build_default_registry
from loregraph.exceptions import (
    AgentSessionNotFoundError,
    AttachmentNotFoundError,
    CampaignError,
    ChatAttachmentLimitExceededError,
    ConfigurationError,
    ConnectionNotFoundError,
    ConnectorConfigInvalidError,
    ConnectorUnavailableError,
    CrossProjectEdgeError,
    EdgeNotFoundError,
    EntityNotFoundError,
    ExportConflictError,
    ExternalDataParseError,
    GenerationError,
    InvalidEdgeReferenceError,
    InvalidIconReferenceError,
    KnowledgeSourceNotFoundError,
    ProjectNotFoundError,
    SkillInputInvalidError,
    UnknownConnectorTypeError,
    UnknownSkillError,
    UnsupportedAttachmentTypeError,
    UnsupportedConnectorCapabilityError,
    UnsupportedExportFormatError,
    error_code,
)
from loregraph.llm.embeddings import EmbeddingProvider, get_embedding_provider
from loregraph.observability import create_tracing
from loregraph.schemas.project_transfer import ProjectExport
from loregraph.services.event_bus import EventBus
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.project_transfer import import_project
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.composition import StoreFactories
from loregraph.storage.sqlite.agent_session_store import SqliteAgentSessionStore
from loregraph.storage.sqlite.attachment_store import SqliteAttachmentStore
from loregraph.storage.sqlite.connection_store import (
    SqliteConnectionEntityLinkStore,
    SqliteConnectionStore,
)
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore
from loregraph.storage.sqlite.knowledge_source_store import SqliteKnowledgeSourceStore
from loregraph.storage.sqlite.project_store import SqliteProjectStore
from loregraph.storage.sqlite.usage_store import SqliteUsageStore
from loregraph.storage.vectorstore.chroma_store import ChromaVectorStore

SEED_DEMO_PROJECT_PATH = Path(__file__).parent / "seed" / "demo_project.json"

logger = logging.getLogger(__name__)


async def _warmup_embedding_provider(embedder: EmbeddingProvider) -> None:
    """Load (and on first run download) the embedding model in the background
    at startup, so the first agent request doesn't stall on it."""
    try:
        logger.info(
            "Warming up embedding model %s (first run downloads it once)…",
            embedder.model_id,
        )
        await embedder.embed(["warmup"])
        logger.info("Embedding model %s is ready", embedder.model_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning(
            "Embedding model warmup failed — it will be retried lazily on "
            "first use (vector indexing degrades to a logged warning).",
            exc_info=True,
        )


async def _seed_demo_project_if_empty(
    session_factory: async_sessionmaker[AsyncSession],
    store_factories: StoreFactories,
    attachments_dir: Path,
) -> None:
    async with session_factory() as session:
        project_store = store_factories.project(session)
        if await project_store.list_projects():
            return
        data = ProjectExport.model_validate_json(
            SEED_DEMO_PROJECT_PATH.read_text(encoding="utf-8")
        )
        await import_project(
            project_store,
            store_factories.entity(session),
            store_factories.edge(session),
            store_factories.attachment(session),
            attachments_dir,
            data,
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    settings.knowledge_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine_for(settings.db_path)
        await init_db(engine)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        # Realtime pub/sub for the whole app lifetime — in-process, one
        # channel per project, created lazily (see services/event_bus.py).
        app.state.event_bus = EventBus()
        # Composition root: the only place that maps storage Protocols to
        # concrete SQLite classes. api/deps.py depends only on this bundle
        # and on the Protocol types, never on loregraph.storage.sqlite.*.
        app.state.store_factories = StoreFactories(
            project=SqliteProjectStore,
            entity=SqliteEntityStore,
            edge=SqliteEdgeStore,
            attachment=lambda session: SqliteAttachmentStore(
                session, settings.attachments_dir
            ),
            agent_session=SqliteAgentSessionStore,
            knowledge_source=lambda session: SqliteKnowledgeSourceStore(
                session, settings.knowledge_dir
            ),
            usage=SqliteUsageStore,
            connection=SqliteConnectionStore,
            connection_entity_link=SqliteConnectionEntityLinkStore,
        )
        # External-tool connectors: the registry maps connector types to
        # implementations; the runtime hosts long-lived clients (Foundry MCP
        # sessions) for the app's lifetime and is closed with the lifespan.
        app.state.connector_registry = build_default_registry()
        app.state.connector_runtime = ConnectorRuntime()
        # Vector layer is optional derived data: None when embeddings are
        # disabled, and the manual editor must keep working either way.
        # knowledge_index reuses the SAME ChromaVectorStore instance as
        # vector_index (different collection namespace, see
        # services/knowledge_index.py) — not a second Chroma client.
        embedder = get_embedding_provider(settings)
        chroma_store = (
            ChromaVectorStore(settings.chroma_dir, embedder)
            if embedder is not None
            else None
        )
        app.state.vector_index = (
            VectorIndex(chroma_store) if chroma_store is not None else None
        )
        app.state.knowledge_index = (
            KnowledgeIndex(chroma_store) if chroma_store is not None else None
        )
        # Off the critical path: startup stays instant, but by the time the
        # user first hits "Generate lore" the model is (usually) loaded.
        warmup_task = (
            asyncio.create_task(_warmup_embedding_provider(embedder))
            if embedder is not None
            else None
        )
        # LangGraph checkpointer: interrupted agent runs must survive process
        # restarts, so the saver lives on disk for the app's whole lifetime.
        async with AsyncExitStack() as stack:
            app.state.agent_checkpointer = await stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(
                    str(settings.agent_checkpoint_db_path)
                )
            )
            await _seed_demo_project_if_empty(
                app.state.session_factory,
                app.state.store_factories,
                settings.attachments_dir,
            )
            tracing = create_tracing(settings)
            if tracing is not None:
                config, lifecycle = tracing
                lifecycle.start()
                app.state.tracing_config = config
                app.state.tracing_lifecycle = lifecycle
            yield
            await app.state.connector_runtime.aclose()
            if hasattr(app.state, "tracing_lifecycle"):
                app.state.tracing_lifecycle.stop()
            if warmup_task is not None and not warmup_task.done():
                warmup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await warmup_task
        await engine.dispose()

    app = FastAPI(title="Loregraph", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)
    _API_PREFIX = "/api"
    app.include_router(projects.router, prefix=_API_PREFIX)
    app.include_router(entities.router, prefix=_API_PREFIX)
    app.include_router(edges.router, prefix=_API_PREFIX)
    app.include_router(graph.router, prefix=_API_PREFIX)
    app.include_router(attachments.router, prefix=_API_PREFIX)
    app.include_router(agent.router, prefix=_API_PREFIX)
    app.include_router(knowledge.router, prefix=_API_PREFIX)
    app.include_router(usage.router, prefix=_API_PREFIX)
    app.include_router(connections.types_router, prefix=_API_PREFIX)
    app.include_router(connections.router, prefix=_API_PREFIX)
    app.include_router(realtime.router, prefix=_API_PREFIX)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/files", StaticFiles(directory=settings.attachments_dir), name="files")

    return app


def _error_response(status_code: int, exc: Exception) -> JSONResponse:
    # `code` is the single machine-readable field the frontend's i18n catalog
    # keys off; `detail` is an English diagnostic string, never translated
    # Deriving `code` from the exception class name (error_code) means
    # a new CampaignError subclass gets a working code with zero boilerplate
    # here — only status codes that aren't the 400 default need a handler.
    return JSONResponse(
        status_code=status_code, content={"code": error_code(exc), "detail": str(exc)}
    )


def _register_exception_handlers(app: FastAPI) -> None:
    _not_found = (
        ProjectNotFoundError,
        EntityNotFoundError,
        EdgeNotFoundError,
        AttachmentNotFoundError,
        AgentSessionNotFoundError,
        KnowledgeSourceNotFoundError,
        ConnectionNotFoundError,
        UnknownSkillError,
    )
    for exc_type in _not_found:
        app.add_exception_handler(exc_type, lambda _r, e: _error_response(404, e))

    _unprocessable = (
        InvalidEdgeReferenceError,
        CrossProjectEdgeError,
        UnsupportedExportFormatError,
        InvalidIconReferenceError,
        UnsupportedAttachmentTypeError,
        ChatAttachmentLimitExceededError,
        UnknownConnectorTypeError,
        ConnectorConfigInvalidError,
        UnsupportedConnectorCapabilityError,
        ExternalDataParseError,
        SkillInputInvalidError,
    )
    for unprocessable_type in _unprocessable:
        app.add_exception_handler(
            unprocessable_type, lambda _r, e: _error_response(422, e)
        )

    app.add_exception_handler(ConfigurationError, lambda _r, e: _error_response(409, e))
    app.add_exception_handler(GenerationError, lambda _r, e: _error_response(502, e))
    app.add_exception_handler(
        ConnectorUnavailableError, lambda _r, e: _error_response(502, e)
    )
    app.add_exception_handler(
        ExportConflictError, lambda _r, e: _error_response(409, e)
    )
    # Fallback for every other CampaignError subclass (including the
    # HITL/session-state guards in api/routers/agent.py) — 400, code still
    # derived automatically from the concrete class.
    app.add_exception_handler(CampaignError, lambda _r, e: _error_response(400, e))


app = create_app()
