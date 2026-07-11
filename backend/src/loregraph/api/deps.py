from collections.abc import AsyncGenerator
from typing import Annotated, cast

from fastapi import Depends, Request
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.graph import build_agent_graph
from loregraph.agent.runner import AgentRunner
from loregraph.config import Settings
from loregraph.llm.factory import get_chat_model
from loregraph.llm.structured import LangChainStructuredGenerator
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.composition import StoreFactories
from loregraph.storage.protocols import (
    AgentSessionStore,
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


def get_vector_index(request: Request) -> VectorIndex | None:
    # None whenever embeddings are disabled — every consumer must degrade
    # gracefully (the manual editor never depends on the vector layer).
    return cast(VectorIndex | None, request.app.state.vector_index)


VectorIndexDep = Annotated[VectorIndex | None, Depends(get_vector_index)]


# Services are concrete classes composed from Protocol stores — no factory
# indirection needed; DIP lives at the store boundary.
async def get_entity_service(
    store: EntityStoreDep, vector_index: VectorIndexDep
) -> EntityService:
    return EntityService(store, vector_index)


async def get_edge_service(
    edge_store: EdgeStoreDep, entity_store: EntityStoreDep
) -> EdgeService:
    return EdgeService(edge_store, entity_store)


EntityServiceDep = Annotated[EntityService, Depends(get_entity_service)]
EdgeServiceDep = Annotated[EdgeService, Depends(get_edge_service)]


async def get_agent_session_store(
    request: Request, session: SessionDep
) -> AgentSessionStore:
    return _factories(request).agent_session(session)


AgentSessionStoreDep = Annotated[AgentSessionStore, Depends(get_agent_session_store)]


async def get_agent_runner(
    request: Request,
    settings: SettingsDep,
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    entity_service: EntityServiceDep,
    edge_service: EdgeServiceDep,
    vector_index: VectorIndexDep,
    agent_sessions: AgentSessionStoreDep,
) -> AgentRunner:
    """Builds the per-request agent graph: services are session-scoped, so
    the graph is compiled per request against the shared checkpointer (state
    lives with the checkpointer/thread_id, not with the compiled object).
    Raises ConfigurationError (→ 409) when no LLM is configured."""
    checkpointer = cast(BaseCheckpointSaver[str], request.app.state.agent_checkpointer)
    generation_model = get_chat_model(settings, tier="generation")
    graph = build_agent_graph(
        chat_model=generation_model,
        creative=LangChainStructuredGenerator(generation_model),
        extraction=LangChainStructuredGenerator(
            get_chat_model(settings, tier="extraction")
        ),
        vector_index=vector_index,
        entity_store=entity_store,
        edge_store=edge_store,
        entity_service=entity_service,
        edge_service=edge_service,
        token_budget=settings.agent_run_token_budget,
        checkpointer=checkpointer,
    )
    return AgentRunner(graph, agent_sessions)


AgentRunnerDep = Annotated[AgentRunner, Depends(get_agent_runner)]
