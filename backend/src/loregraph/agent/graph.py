from functools import partial

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from loregraph.agent.nodes.assistant import (
    assistant,
    begin_edit,
    begin_proposal,
    route_after_assistant,
)
from loregraph.agent.nodes.check_duplicates import (
    check_duplicates_draft,
    check_duplicates_request,
    route_after_draft_check,
)
from loregraph.agent.nodes.commit import commit
from loregraph.agent.nodes.generate_edit import generate_edit
from loregraph.agent.nodes.generate_lore import generate_lore
from loregraph.agent.nodes.human_review import human_review, route_after_review
from loregraph.agent.nodes.retrieve_context import retrieve_context
from loregraph.agent.nodes.tools import run_tools
from loregraph.agent.nodes.verify_grounding import verify_grounding
from loregraph.agent.state import AgentState
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
        ),
    )
    builder.add_node(
        "tools",
        partial(
            run_tools,
            vector_index=vector_index,
            knowledge_index=knowledge_index,
            entity_store=entity_store,
        ),
    )
    builder.add_node("begin_proposal", begin_proposal)
    builder.add_node("begin_edit", begin_edit)

    # --- Proposal pipeline (unchanged core)
    builder.add_node(
        "retrieve_context",
        partial(
            retrieve_context,
            vector_index=vector_index,
            knowledge_index=knowledge_index,
            entity_store=entity_store,
            edge_store=edge_store,
        ),
    )
    builder.add_node(
        "check_duplicates_request",
        partial(check_duplicates_request, entity_store=entity_store),
    )
    builder.add_node(
        "generate_lore",
        partial(
            generate_lore,
            creative=creative,
            token_budget=token_budget,
            project_store=project_store,
            usage_store=usage_store,
            model_name=generation_model_name,
        ),
    )
    builder.add_node(
        "check_duplicates_draft",
        partial(check_duplicates_draft, entity_store=entity_store),
    )
    builder.add_node(
        "verify_grounding",
        partial(
            verify_grounding,
            extraction=extraction,
            token_budget=token_budget,
            usage_store=usage_store,
            model_name=extraction_model_name,
        ),
    )
    builder.add_node("human_review", human_review)
    builder.add_node(
        "commit",
        partial(commit, entity_service=entity_service, edge_service=edge_service),
    )

    # ── Edit pipeline ───────────────────────────────────────────────────────────
    builder.add_node(
        "generate_edit",
        partial(
            generate_edit,
            creative=creative,
            token_budget=token_budget,
            entity_store=entity_store,
            project_store=project_store,
            usage_store=usage_store,
            model_name=generation_model_name,
        ),
    )

    builder.add_edge(START, "assistant")
    builder.add_conditional_edges(
        "assistant",
        route_after_assistant,
        {"tools": "tools", "propose": "begin_proposal", "edit": "begin_edit", "end": END},
    )
    builder.add_edge("tools", "assistant")

    builder.add_edge("begin_proposal", "retrieve_context")
    builder.add_edge("retrieve_context", "check_duplicates_request")
    builder.add_edge("check_duplicates_request", "generate_lore")
    builder.add_edge("generate_lore", "check_duplicates_draft")
    builder.add_conditional_edges(
        "check_duplicates_draft",
        route_after_draft_check,
        {"retry": "generate_lore", "continue": "verify_grounding"},
    )
    builder.add_edge("verify_grounding", "human_review")
    builder.add_conditional_edges(
        "human_review",
        route_after_review,
        {"revise": "generate_lore", "commit": "commit"},
    )
    builder.add_edge("commit", END)

    # Edit pipeline edges (skips retrieve/dedup/verify — not applicable to
    # targeted single-entity edits).
    builder.add_edge("begin_edit", "generate_edit")
    builder.add_edge("generate_edit", "human_review")
    # human_review → commit already wired above; commit → END already wired.

    return builder.compile(checkpointer=checkpointer)
