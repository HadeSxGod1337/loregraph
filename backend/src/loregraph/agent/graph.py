from functools import partial

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from loregraph.agent.mcp_tools import McpToolProvider
from loregraph.agent.nodes.assistant import (
    assistant,
    begin_changes,
    route_after_assistant,
)
from loregraph.agent.nodes.commit import commit
from loregraph.agent.nodes.generate_changes import generate_changes
from loregraph.agent.nodes.human_review import human_review, route_after_review
from loregraph.agent.nodes.retrieve_context import retrieve_context
from loregraph.agent.nodes.tools import run_tools
from loregraph.agent.nodes.validate_changes import (
    route_after_validate,
    validate_changes,
)
from loregraph.agent.skills.registry import SKILLS
from loregraph.agent.state import AgentState
from loregraph.connectors.live import LiveSourceProvider
from loregraph.llm.structured import StructuredGenerator
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.knowledge_index import KnowledgeIndex
from loregraph.services.vector_index import VectorIndex
from loregraph.storage.protocols import (
    EdgeStore,
    EntityStore,
    ProjectStore,
    UsageStore,
)


def build_agent_graph(
    *,
    chat_model: BaseChatModel,
    creative: StructuredGenerator,
    extraction: StructuredGenerator,
    vector_index: VectorIndex | None,
    knowledge_index: KnowledgeIndex | None,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    project_store: ProjectStore,
    entity_service: EntityService,
    edge_service: EdgeService,
    token_budget: int,
    checkpointer: BaseCheckpointSaver[str] | None,
    usage_store: UsageStore | None = None,
    # Resolved model ids, for per-model token attribution. The nodes get the
    # id of the model actually behind their injected client, since the
    # BaseChatModel/StructuredGenerator abstractions deliberately hide it.
    assistant_model_name: str = "",
    generation_model_name: str = "",
    extraction_model_name: str = "",
    # Live external sources (Foundry, LSS…) — None when the project has no
    # live-capable connections; the assistant then never sees the tool.
    live_sources: LiveSourceProvider | None = None,
    # Generic MCP passthrough tools (any stdio MCP server the game master
    # connects) — None when the project has no such connections.
    mcp_tools: McpToolProvider | None = None,
) -> CompiledStateGraph[AgentState]:
    """Conversational assistant with a lore-proposal pipeline.

    assistant answers questions (grounded via read tools) and asks clarifying
    questions; creating content is only possible through the propose_lore
    tool, which routes into the draft pipeline with its mandatory
    human_review interrupt. HITL invariant is structural: only the commit
    node receives the write services.
    """
    builder: StateGraph[AgentState] = StateGraph(AgentState)

    # --- Conversation loop
    builder.add_node(
        "assistant",
        partial(
            assistant,
            chat_model=chat_model,
            token_budget=token_budget,
            project_store=project_store,
            usage_store=usage_store,
            model_name=assistant_model_name,
            live_sources=live_sources,
            mcp_tools=mcp_tools,
        ),
    )
    builder.add_node(
        "tools",
        partial(
            run_tools,
            vector_index=vector_index,
            knowledge_index=knowledge_index,
            entity_store=entity_store,
            edge_store=edge_store,
            live_sources=live_sources,
            mcp_tools=mcp_tools,
        ),
    )
    builder.add_node("begin_changes", begin_changes)

    # --- Unified proposal pipeline: one path for create + edit + relate.
    builder.add_node(
        "retrieve_context",
        partial(
            retrieve_context,
            vector_index=vector_index,
            knowledge_index=knowledge_index,
            entity_store=entity_store,
            edge_store=edge_store,
            live_sources=live_sources,
        ),
    )
    builder.add_node(
        "generate_changes",
        partial(
            generate_changes,
            creative=creative,
            token_budget=token_budget,
            project_store=project_store,
            usage_store=usage_store,
            model_name=generation_model_name,
        ),
    )
    builder.add_node(
        "validate_changes",
        partial(
            validate_changes,
            extraction=extraction,
            token_budget=token_budget,
            entity_store=entity_store,
            edge_store=edge_store,
            usage_store=usage_store,
            model_name=extraction_model_name,
        ),
    )
    builder.add_node("human_review", human_review)
    builder.add_node(
        "commit",
        partial(commit, entity_service=entity_service, edge_service=edge_service),
    )

    # Every "propose"/"job" skill's entry_node is a valid route_after_
    # assistant target (chat tool-call dispatch) AND a valid START target
    # (direct skill_kickoff, bypassing the assistant LLM entirely — see
    # agent/skills/registry.py, api/routers/agent.py's skill-run endpoint).
    # Built from the registry so a new skill needs no change here beyond its
    # own node/edges.
    skill_entry_nodes = {
        manifest.entry_node
        for manifest in SKILLS.values()
        if manifest.kind in ("propose", "job") and manifest.entry_node
    }

    def route_entry(state: AgentState) -> str:
        if state.skill_kickoff is not None:
            entry_node = SKILLS[state.skill_kickoff.skill].entry_node
            assert entry_node is not None
            return entry_node
        return "assistant"

    builder.add_conditional_edges(
        START,
        route_entry,
        {"assistant": "assistant", **{node: node for node in skill_entry_nodes}},
    )
    builder.add_conditional_edges(
        "assistant",
        route_after_assistant,
        {"tools": "tools", "end": END, **{node: node for node in skill_entry_nodes}},
    )
    builder.add_edge("tools", "assistant")

    # Single write pipeline: retrieve grounding (including the explicit edit
    # targets in full) → generate the whole proposal → validate it (dedup,
    # relationship + patch checks, grounding) → review → commit.
    builder.add_edge("begin_changes", "retrieve_context")
    builder.add_edge("retrieve_context", "generate_changes")
    builder.add_edge("generate_changes", "validate_changes")
    builder.add_conditional_edges(
        "validate_changes",
        route_after_validate,
        {"retry": "generate_changes", "continue": "human_review"},
    )
    builder.add_conditional_edges(
        "human_review",
        route_after_review,
        {"revise": "generate_changes", "commit": "commit"},
    )
    builder.add_edge("commit", END)

    return builder.compile(checkpointer=checkpointer)
