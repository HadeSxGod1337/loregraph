import logging
from collections.abc import AsyncGenerator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession

from loregraph.agent.graph import build_agent_graph
from loregraph.agent.import_graph import build_import_graph
from loregraph.agent.import_runner import ImportJobRunner
from loregraph.agent.import_source import ImportSourceResolver
from loregraph.agent.mcp_tools import McpConnection, McpToolProvider
from loregraph.agent.runner import AgentRunner
from loregraph.api.security import (
    MasterAuthenticatorDep,
    MasterIdentity,
    PlayerIdentity,
    extract_player_token,
    hash_token,
)
from loregraph.config import Settings
from loregraph.connectors.context import ConnectorContext
from loregraph.connectors.live import LiveSourceEntry, LiveSourceProvider
from loregraph.connectors.protocols import (
    CAPABILITY_LIVE,
    CAPABILITY_MCP_TOOLS,
    IngestSource,
    LiveSource,
    McpToolSource,
)
from loregraph.connectors.registry import ConnectorRegistry
from loregraph.connectors.runtime import ConnectorRuntime
from loregraph.exceptions import (
    CampaignError,
    ConnectionNotFoundError,
    InvalidPlayerTokenError,
    UnsupportedConnectorCapabilityError,
)
from loregraph.llm.factory import get_chat_model
from loregraph.llm.structured import LangChainStructuredGenerator
from loregraph.schemas.connection import ConnectionOut
from loregraph.services.connector_push import ConnectorPushService
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.entity_template_service import EntityTemplateService
from loregraph.services.event_bus import EventBus
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.player_view import PlayerViewService
from loregraph.services.sheet_preset_service import SheetPresetService
from loregraph.services.update_status import UpdateService, app_version
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.composition import StoreFactories
from loregraph.storage.protocols import (
    AgentSessionStore,
    AttachmentStore,
    ConnectionEntityLinkStore,
    ConnectionStore,
    EdgeStore,
    EntityStore,
    EntityTemplateStore,
    ImportJobStore,
    KnowledgeSourceStore,
    PlayerNoteStore,
    PlayerStore,
    ProjectStore,
    SheetPresetStore,
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


async def get_entity_template_store(
    request: Request, session: SessionDep
) -> EntityTemplateStore:
    return _factories(request).entity_template(session)


async def get_sheet_preset_store(
    request: Request, session: SessionDep
) -> SheetPresetStore:
    return _factories(request).sheet_preset(session)


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
EntityTemplateStoreDep = Annotated[
    EntityTemplateStore, Depends(get_entity_template_store)
]
SheetPresetStoreDep = Annotated[SheetPresetStore, Depends(get_sheet_preset_store)]
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


def get_update_service(settings: SettingsDep) -> UpdateService:
    return UpdateService(settings.data_dir, app_version())


UpdateServiceDep = Annotated[UpdateService, Depends(get_update_service)]


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


async def get_entity_template_service(
    store: EntityTemplateStoreDep,
) -> EntityTemplateService:
    return EntityTemplateService(store)


async def get_sheet_preset_service(
    store: SheetPresetStoreDep,
) -> SheetPresetService:
    return SheetPresetService(store)


EntityServiceDep = Annotated[EntityService, Depends(get_entity_service)]
EdgeServiceDep = Annotated[EdgeService, Depends(get_edge_service)]
EntityTemplateServiceDep = Annotated[
    EntityTemplateService, Depends(get_entity_template_service)
]
SheetPresetServiceDep = Annotated[SheetPresetService, Depends(get_sheet_preset_service)]


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


async def get_player_store(request: Request, session: SessionDep) -> PlayerStore:
    return _factories(request).player(session)


async def get_player_note_store(
    request: Request, session: SessionDep
) -> PlayerNoteStore:
    return _factories(request).player_note(session)


PlayerStoreDep = Annotated[PlayerStore, Depends(get_player_store)]
PlayerNoteStoreDep = Annotated[PlayerNoteStore, Depends(get_player_note_store)]


async def get_player_view_service(
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    note_store: PlayerNoteStoreDep,
) -> PlayerViewService:
    return PlayerViewService(entity_store, edge_store, note_store)


PlayerViewServiceDep = Annotated[
    PlayerViewService, Depends(get_player_view_service)
]


async def get_optional_player_identity(
    request: Request, player_store: PlayerStoreDep
) -> PlayerIdentity | None:
    """The player behind a play token, or None when there's no valid one.
    project_id comes from the token — never the URL — so a token can't address
    another project."""
    token = extract_player_token(request)
    if token is None:
        return None
    player = await player_store.find_active_by_token_hash(hash_token(token))
    if player is None:
        return None
    await player_store.touch_last_seen(player.id)
    return PlayerIdentity(
        player_id=player.id, project_id=player.project_id, name=player.name
    )


OptionalPlayerIdentityDep = Annotated[
    PlayerIdentity | None, Depends(get_optional_player_identity)
]


async def require_player(identity: OptionalPlayerIdentityDep) -> PlayerIdentity:
    if identity is None:
        raise InvalidPlayerTokenError()
    return identity


PlayerIdentityDep = Annotated[PlayerIdentity, Depends(require_player)]


async def get_master_or_player_identity(
    request: Request,
    auth: MasterAuthenticatorDep,
    player_store: PlayerStoreDep,
) -> MasterIdentity | PlayerIdentity:
    """Either the DM (loopback) or a valid player. Used where both may read the
    same resource under different rules — the attachment route resolves the
    file, then decides access from which identity this returned."""
    master = await auth.identify(request)
    if master is not None:
        return master
    player = await get_optional_player_identity(request, player_store)
    if player is not None:
        return player
    raise HTTPException(status_code=401, detail="Master or player access required")


IdentityDep = Annotated[
    MasterIdentity | PlayerIdentity, Depends(get_master_or_player_identity)
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
    """Generic MCP tool connections of this project — the McpToolSource
    analog of get_live_source_provider.

    Built lazily: this only assembles the connectors (cheap — construction
    spawns no MCP server); the actual tool catalog is fetched on the first
    discover/call, so a chat turn that never touches MCP costs no bridge
    spawn and no list round-trip. None when the project has no such
    connections. A misconfigured connection is skipped with a warning
    instead of breaking the whole agent — same graceful-degradation contract
    as live sources."""
    connections = await connection_store.list_for_project(project_id)
    mcp_connections: list[McpConnection] = []
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
        except CampaignError:
            logger.warning(
                "Skipping MCP tool source %s (%s): connector could not be built",
                connection.name,
                connection.connector_type,
                exc_info=True,
            )
            continue
        if not isinstance(connector, McpToolSource):
            continue
        mcp_connections.append(
            McpConnection(
                name=connection.name,
                connector_type=connection.connector_type,
                source=connector,
            )
        )
    return McpToolProvider(mcp_connections) if mcp_connections else None


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
    connection_store: ConnectionStoreDep,
    link_store: ConnectionEntityLinkStoreDep,
    registry: ConnectorRegistryDep,
    runtime: ConnectorRuntimeDep,
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    attachment_store: AttachmentStoreDep,
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

    async def connection_ingest_factory(
        project_id: str, connection_id: str
    ) -> IngestSource:
        """Resolve a connection to an IngestSource for the migration path —
        same connector-resolution pattern as get_live_source_provider, kept
        out of the agent layer (see agent/import_source.py's docstring). Only
        invoked by plan_windows when source_kind == "connection", i.e. never
        for the file-import path."""
        connection = await connection_store.get(connection_id)
        if connection.project_id != project_id:
            raise ConnectionNotFoundError(connection_id)
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
        if not isinstance(connector, IngestSource):
            raise UnsupportedConnectorCapabilityError(
                connection.connector_type, "ingest"
            )
        return connector

    source_resolver = ImportSourceResolver(source_store, connection_ingest_factory)
    # Both the registry pass and the entity-extraction pass are
    # classification/extraction-shaped work (CLAUDE.md: "Haiku —
    # классификация/экстракция... низкая температура"), not the free
    # creative generation propose_lore does — neither belongs on the
    # pricier "generation" tier tuned for creative temperature.
    extraction_model = get_chat_model(settings, tier="extraction")
    graph = build_import_graph(
        extraction=LangChainStructuredGenerator(extraction_model),
        creative=LangChainStructuredGenerator(extraction_model),
        source_resolver=source_resolver,
        entity_store=entity_store,
        entity_service=entity_service,
        edge_service=edge_service,
        checkpointer=checkpointer,
        event_bus=event_bus,
    )
    return ImportJobRunner(graph, import_jobs)


ImportJobRunnerDep = Annotated[ImportJobRunner, Depends(get_import_job_runner)]
