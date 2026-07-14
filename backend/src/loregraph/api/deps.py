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
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.composition import StoreFactories
from loregraph.storage.protocols import (
    AgentSessionStore,
    AttachmentStore,
    EdgeStore,
    EntityStore,
    KnowledgeSourceStore,
    ProjectStore,
    UsageStore,
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


async def get_knowledge_source_store(
    request: Request, session: SessionDep
) -> KnowledgeSourceStore:
    return _factories(request).knowledge_source(session)


async def get_usage_store(request: Request, session: SessionDep) -> UsageStore:
    return _factories(request).usage(session)


ProjectStoreDep = Annotated[ProjectStore, Depends(get_project_store)]
EntityStoreDep = Annotated[EntityStore, Depends(get_entity_store)]
EdgeStoreDep = Annotated[EdgeStore, Depends(get_edge_store)]
AttachmentStoreDep = Annotated[AttachmentStore, Depends(get_attachment_store)]
KnowledgeSourceStoreDep = Annotated[
    KnowledgeSourceStore, Depends(get_knowledge_source_store)
]
UsageStoreDep = Annotated[UsageStore, Depends(get_usage_store)]


def get_vector_index(request: Request) -> VectorIndex | None:
    # None whenever embeddings are disabled — every consumer must degrade
    # gracefully (the manual editor never depends on the vector layer).
    return cast(VectorIndex | None, request.app.state.vector_index)


VectorIndexDep = Annotated[VectorIndex | None, Depends(get_vector_index)]


def get_knowledge_index(request: Request) -> KnowledgeIndex | None:
    # Same optionality contract as get_vector_index: None when embeddings are
    # disabled, every consumer degrades (see services/knowledge_ingest.py).
    return cast(KnowledgeIndex | None, request.app.state.knowledge_index)


KnowledgeIndexDep = Annotated[KnowledgeIndex | None, Depends(get_knowledge_index)]


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
    project_store: ProjectStoreDep,
    entity_service: EntityServiceDep,
    edge_service: EdgeServiceDep,
    vector_index: VectorIndexDep,
    knowledge_index: KnowledgeIndexDep,
    agent_sessions: AgentSessionStoreDep,
    usage_store: UsageStoreDep,
) -> AgentRunner:
    """Builds the per-request agent graph: services are session-scoped, so
    the graph is compiled per request against the shared checkpointer (state
    lives with the checkpointer/thread_id, not with the compiled object).
    Raises ConfigurationError (→ 409) when no LLM is configured."""
    checkpointer = cast(BaseCheckpointSaver[str], request.app.state.agent_checkpointer)
    # Three tiers, three roles: the chat loop is the highest-frequency caller
    # and only routes tools / writes short replies, so it runs on the cheap
    # `assistant` model rather than sharing the pricier creative one.
    assistant_model = get_chat_model(settings, tier="assistant")
    generation_model = get_chat_model(settings, tier="generation")
    extraction_model = get_chat_model(settings, tier="extraction")
    # Prompt caching is an Anthropic feature; other providers get the same
    # prompt as one plain block (see llm/structured.py).
    prompt_caching = settings.agent_prompt_caching and settings.llm_provider == (
        "anthropic"
    )
    graph = build_agent_graph(
        chat_model=assistant_model,
        creative=LangChainStructuredGenerator(
            generation_model, prompt_caching=prompt_caching
        ),
        extraction=LangChainStructuredGenerator(extraction_model),
        vector_index=vector_index,
        knowledge_index=knowledge_index,
        entity_store=entity_store,
        edge_store=edge_store,
        project_store=project_store,
        entity_service=entity_service,
        edge_service=edge_service,
        token_budget=settings.agent_run_token_budget,
        checkpointer=checkpointer,
        usage_store=usage_store,
        assistant_model_name=settings.llm_model_assistant,
        generation_model_name=settings.llm_model_generation,
        extraction_model_name=settings.llm_model_extraction,
    )
    return AgentRunner(graph, agent_sessions)


AgentRunnerDep = Annotated[AgentRunner, Depends(get_agent_runner)]
