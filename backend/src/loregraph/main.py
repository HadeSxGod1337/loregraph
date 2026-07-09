from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from loregraph.api.routers import attachments, edges, entities, graph
from loregraph.config import Settings
from loregraph.exceptions import (
    AttachmentNotFoundError,
    CampaignError,
    EdgeNotFoundError,
    EntityNotFoundError,
    InvalidEdgeReferenceError,
    InvalidIconReferenceError,
)
from loregraph.storage.composition import StoreFactories
from loregraph.storage.sqlite.attachment_store import SqliteAttachmentStore
from loregraph.storage.sqlite.db import (
    create_engine_for,
    init_db,
    make_session_factory,
)
from loregraph.storage.sqlite.edge_store import SqliteEdgeStore
from loregraph.storage.sqlite.entity_store import SqliteEntityStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine_for(settings.db_path)
        await init_db(engine)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        # Composition root: the only place that maps storage Protocols to
        # concrete SQLite classes. api/deps.py depends only on this bundle
        # and on the Protocol types, never on loregraph.storage.sqlite.*.
        app.state.store_factories = StoreFactories(
            entity=SqliteEntityStore,
            edge=SqliteEdgeStore,
            attachment=lambda session: SqliteAttachmentStore(
                session, settings.attachments_dir
            ),
        )
        yield
        await engine.dispose()

    app = FastAPI(title="Loregraph", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)

    app.include_router(entities.router, prefix="/api")
    app.include_router(edges.router, prefix="/api")
    app.include_router(graph.router, prefix="/api")
    app.include_router(attachments.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/files", StaticFiles(directory=settings.attachments_dir), name="files")

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(EntityNotFoundError)
    async def _entity_not_found(
        _request: Request, exc: EntityNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(EdgeNotFoundError)
    async def _edge_not_found(
        _request: Request, exc: EdgeNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(AttachmentNotFoundError)
    async def _attachment_not_found(
        _request: Request, exc: AttachmentNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidEdgeReferenceError)
    async def _invalid_edge_reference(
        _request: Request, exc: InvalidEdgeReferenceError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(InvalidIconReferenceError)
    async def _invalid_icon_reference(
        _request: Request, exc: InvalidIconReferenceError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(CampaignError)
    async def _campaign_error(_request: Request, exc: CampaignError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


app = create_app()
