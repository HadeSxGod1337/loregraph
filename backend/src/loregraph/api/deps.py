from collections.abc import AsyncGenerator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.config import Settings
from loregraph.storage.composition import StoreFactories
from loregraph.storage.protocols import (
    AttachmentStore,
    EdgeStore,
    EntityStore,
    ProjectStore,
)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        await session.close()


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


SettingsDep = Annotated[Settings, Depends(get_settings)]


def _factories(request: Request) -> StoreFactories:
    # app.state is dynamically typed (Starlette State.__getattr__ -> Any); this
    # cast is the one place that asserts its real shape for the type checker.
    return cast(StoreFactories, request.app.state.store_factories)


async def get_project_store(request: Request, session: SessionDep) -> ProjectStore:
    return _factories(request).project(session)


async def get_entity_store(request: Request, session: SessionDep) -> EntityStore:
    return _factories(request).entity(session)


async def get_edge_store(request: Request, session: SessionDep) -> EdgeStore:
    return _factories(request).edge(session)


async def get_attachment_store(
    request: Request, session: SessionDep
) -> AttachmentStore:
    return _factories(request).attachment(session)


ProjectStoreDep = Annotated[ProjectStore, Depends(get_project_store)]
EntityStoreDep = Annotated[EntityStore, Depends(get_entity_store)]
EdgeStoreDep = Annotated[EdgeStore, Depends(get_edge_store)]
AttachmentStoreDep = Annotated[AttachmentStore, Depends(get_attachment_store)]
