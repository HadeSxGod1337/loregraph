import logging
from collections.abc import AsyncGenerator
from typing import Annotated, cast

from fastapi import Depends, Request
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.graph import build_agent_graph
from loregraph.agent.import_graph import build_import_graph
from loregraph.agent.import_runner import ImportJobRunner
from loregraph.agent.mcp_tools import McpToolEntry, McpToolProvider
from loregraph.agent.runner import AgentRunner
from loregraph.config import Settings
from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.live import LiveSourceEntry, LiveSourceProvider
from loregraph.connectors.protocols import (
    CAPABILITY_LIVE,
    CAPABILITY_MCP_TOOLS,
    LiveSource,
    McpToolSource,
)
from loregraph.connectors.registry import ConnectorRegistry
from loregraph.connectors.runtime import ConnectorRuntime
from loregraph.exceptions import CampaignError
from loregraph.llm.factory import get_chat_model
from loregraph.llm.structured import LangChainStructuredGenerator
from loregraph.schemas.connection import ConnectionOut
from loregraph.services.connector_push import ConnectorPushService
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.event_bus import EventBus
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.composition import StoreFactories
from loregraph.storage.protocols import (
    AgentSessionStore,
    AttachmentStore,
    ConnectionEntityLinkStore,
    ConnectionStore,
    EdgeStore,
    EntityStore,
    ImportJobStore,
    KnowledgeSourceStore,
    ProjectStore,
    UsageStore,
)

logger = logging.getLogger(__name__)


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


def get_event_bus(request: Request) -> EventBus:
    return cast(EventBus, request.app.state.event_bus)


EventBusDep = Annotated[EventBus, Depends(get_event_bus)]


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


async def get_import_job_store(request: Request, session: SessionDep) -> ImportJobStore:
    return _factories(request).import_job(session)


ImportJobStoreDep = Annotated[ImportJobStore, Depends(get_import_job_store)]


async def get_connection_store(
    request: Request, session: SessionDep
) -> ConnectionStore:
    return _factories(request).connection(session)


async def get_connection_entity_link_store(
    request: Request, session: SessionDep
) -> ConnectionEntityLinkStore:
    return _factories(request).connection_entity_link(session)


ConnectionStoreDep = Annotated[ConnectionStore, Depends(get_connection_store)]
ConnectionEntityLinkStoreDep = Annotated[
    ConnectionEntityLinkStore, Depends(get_connection_entity_link_store)
]


def get_connector_registry(request: Request) -> ConnectorRegistry:
    return cast(ConnectorRegistry, request.app.state.connector_registry)


def get_connector_runtime(request: Request) -> ConnectorRuntime:
    return cast(ConnectorRuntime, request.app.state.connector_runtime)


ConnectorRegistryDep = Annotated[ConnectorRegistry, Depends(get_connector_registry)]
ConnectorRuntimeDep = Annotated[ConnectorRuntime, Depends(get_connector_runtime)]


async def get_live_source_provider(
    project_id: str,
    settings: SettingsDep,
    connection_store: ConnectionStoreDep,
    link_store: ConnectionEntityLinkStoreDep,
    registry: ConnectorRegistryDep,
    runtime: ConnectorRuntimeDep,
    entity_service: EntityServiceDep,
    edge_service: EdgeServiceDep,
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    attachment_store: AttachmentStoreDep,
) -> LiveSourceProvider | None:
    """Live-capable connections of this project, as agent query sources.

    None when the project has no such connections — the assistant then never
    even sees the query_external_source tool. A misconfigured connection is
    skipped with a warning instead of breaking the whole agent."""
    connections = await connection_store.list_for_project(project_id)
    entries: list[LiveSourceEntry] = []
    for connection in connections:
        try:
            descriptor = registry.get(connection.connector_type)
            if CAPABILITY_LIVE not in descriptor.capabilities:
                continue
            context = ConnectorContext(
                project_id=connection.project_id,
                connection_id=connection.id,
                connection_name=connection.name,
                entity_service=entity_service,
                edge_service=edge_service,
                entity_store=entity_store,
                edge_store=edge_store,
                attachment_store=attachment_store,
                attachments_dir=settings.attachments_dir,
                link_store=link_store,
                runtime=runtime,
            )
            connector = registry.create(
                connection.connector_type, connection.config, context
            )
        except CampaignError:
            logger.warning(
                "Skipping live source %s (%s): connector could not be built",
                connection.name,
                connection.connector_type,
                exc_info=True,
            )
            continue
        if isinstance(connector, LiveSource):
            entries.append(
                LiveSourceEntry(
                    name=connection.name,
                    connector_type=connection.connector_type,
                    use_for_grounding=connection.use_for_grounding,
                    source=connector,
                )
            )
    return LiveSourceProvider(entries) if entries else None


LiveSourceProviderDep = Annotated[
    LiveSourceProvider | None, Depends(get_live_source_provider)
]


async def get_mcp_tool_provider(
    project_id: str,
    settings: SettingsDep,
    connection_store: ConnectionStoreDep,
    link_store: ConnectionEntityLinkStoreDep,
    registry: ConnectorRegistryDep,
    runtime: ConnectorRuntimeDep,
    entity_service: EntityServiceDep,
    edge_service: EdgeServiceDep,
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    attachment_store: AttachmentStoreDep,
) -> McpToolProvider | None:
    """Generic MCP tool sources of this project's connections — the
    McpToolSource analog of get_live_source_provider, one entry per tool
    the server actually exposes (so the assistant binds each tool under its
    own real name/schema, not one generic wrapper tool).

    None when the project has no such connections. A connection whose
    server can't be reached (or isn't configured correctly) is skipped with
    a warning instead of breaking the whole agent turn — same graceful-
    degradation contract as live sources."""
    connections = await connection_store.list_for_project(project_id)
    entries: list[McpToolEntry] = []
    for connection in connections:
        try:
            descriptor = registry.get(connection.connector_type)
            if CAPABILITY_MCP_TOOLS not in descriptor.capabilities:
                continue
            context = ConnectorContext(
                project_id=connection.project_id,
                connection_id=connection.id,
                connection_name=connection.name,
                entity_service=entity_service,
                edge_service=edge_service,
                entity_store=entity_store,
                edge_store=edge_store,
                attachment_store=attachment_store,
                attachments_dir=settings.attachments_dir,
                link_store=link_store,
                runtime=runtime,
            )
            connector = registry.create(
                connection.connector_type, connection.config, context
            )
            if not isinstance(connector, McpToolSource):
                continue
            tools = await connector.list_mcp_tools()
        except CampaignError:
            logger.warning(
                "Skipping MCP tool source %s (%s): connector could not be "
                "built or its tools listed",
                connection.name,
                connection.connector_type,
                exc_info=True,
            )
            continue
        entries.extend(
            McpToolEntry(
                connection_name=connection.name,
                connector_type=connection.connector_type,
                tool=tool,
                source=connector,
            )
            for tool in tools
        )
    return McpToolProvider(entries) if entries else None


McpToolProviderDep = Annotated[McpToolProvider | None, Depends(get_mcp_tool_provider)]


async def get_connector_push_service(
    settings: SettingsDep,
    connection_store: ConnectionStoreDep,
    link_store: ConnectionEntityLinkStoreDep,
    registry: ConnectorRegistryDep,
    runtime: ConnectorRuntimeDep,
    entity_service: EntityServiceDep,
    edge_service: EdgeServiceDep,
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    attachment_store: AttachmentStoreDep,
) -> ConnectorPushService:
    def context_builder(connection: ConnectionOut) -> ConnectorContext:
        return ConnectorContext(
            project_id=connection.project_id,
            connection_id=connection.id,
            connection_name=connection.name,
            entity_service=entity_service,
            edge_service=edge_service,
            entity_store=entity_store,
            edge_store=edge_store,
            attachment_store=attachment_store,
            attachments_dir=settings.attachments_dir,
            link_store=link_store,
            runtime=runtime,
        )

    return ConnectorPushService(connection_store, registry, context_builder)


ConnectorPushServiceDep = Annotated[
    ConnectorPushService, Depends(get_connector_push_service)
]


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
    live_sources: LiveSourceProviderDep,
    mcp_tools: McpToolProviderDep,
    push_service: ConnectorPushServiceDep,
    event_bus: EventBusDep,
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
        live_sources=live_sources,
        mcp_tools=mcp_tools,
    )
    tracing_config = getattr(request.app.state, "tracing_config", None)
    return AgentRunner(
        graph,
        agent_sessions,
        tracing_config=tracing_config,
        push_service=push_service,
        event_bus=event_bus,
    )


AgentRunnerDep = Annotated[AgentRunner, Depends(get_agent_runner)]


async def get_import_job_runner(
    request: Request,
    settings: SettingsDep,
    source_store: KnowledgeSourceStoreDep,
    entity_store: EntityStoreDep,
    entity_service: EntityServiceDep,
    edge_service: EdgeServiceDep,
    import_jobs: ImportJobStoreDep,
    event_bus: EventBusDep,
) -> ImportJobRunner:
    """Builds the per-request bulk-import graph — same rationale as
    get_agent_runner (services are session-scoped, graph is compiled per
    request against the shared import_checkpointer). Raises
    ConfigurationError (→ 409) when no LLM is configured, same as the chat
    graph."""
    checkpointer = cast(BaseCheckpointSaver[str], request.app.state.import_checkpointer)
    # Both the registry pass and the entity-extraction pass are
    # classification/extraction-shaped work (CLAUDE.md: "Haiku —
    # классификация/экстракция... низкая температура"), not the free
    # creative generation propose_lore does — neither belongs on the
    # pricier "generation" tier tuned for creative temperature.
    extraction_model = get_chat_model(settings, tier="extraction")
    graph = build_import_graph(
        extraction=LangChainStructuredGenerator(extraction_model),
        creative=LangChainStructuredGenerator(extraction_model),
        source_store=source_store,
        entity_store=entity_store,
        entity_service=entity_service,
        edge_service=edge_service,
        checkpointer=checkpointer,
        event_bus=event_bus,
    )
    return ImportJobRunner(graph, import_jobs)


ImportJobRunnerDep = Annotated[ImportJobRunner, Depends(get_import_job_runner)]
