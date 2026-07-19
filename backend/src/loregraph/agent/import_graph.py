from functools import partial

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from loregraph.agent.import_state import ImportState
from loregraph.agent.nodes.import_commit import (
    advance_slice,
    commit_relationships,
    commit_slice,
    route_after_advance,
)
from loregraph.agent.nodes.import_extract import extract_windows
from loregraph.agent.nodes.import_merge import merge_extractions
from loregraph.agent.nodes.import_plan import plan_windows
from loregraph.agent.nodes.import_registry import build_registry
from loregraph.agent.nodes.import_review import (
    paginate_review,
    review_slice,
    route_after_slice_review,
)
from loregraph.llm.structured import StructuredGenerator
from loregraph.services.edge_service import EdgeService
from loregraph.services.entity_service import EntityService
from loregraph.services.event_bus import EventBus
from loregraph.storage.protocols import EntityStore, KnowledgeSourceStore


def build_import_graph(
    *,
    extraction: StructuredGenerator,
    creative: StructuredGenerator,
    source_store: KnowledgeSourceStore,
    entity_store: EntityStore,
    entity_service: EntityService,
    edge_service: EdgeService,
    checkpointer: BaseCheckpointSaver[str] | None,
    event_bus: EventBus | None = None,
) -> CompiledStateGraph[ImportState]:
    """Bulk document-import pipeline: a map-reduce job, not a chat turn —
    deliberately its own compiled graph over ImportState rather than a
    branch inside build_agent_graph's AgentState (see agent/import_state.py
    module docstring).

    Fan-out (build_registry, extract_windows) is real asyncio concurrency
    (a TaskGroup/gather + semaphore inside one node), not LangGraph's Send
    API — every per-window call is independent and non-interrupting, so a
    plain gather is simpler and sidesteps Send's less-obvious per-branch
    state-payload semantics for a Pydantic-typed state. The one documented
    hazard this avoids either way: interrupt() must never sit inside a
    parallel branch (confirmed via LangGraph's docs — resuming an interrupt
    re-executes its node from the top, which is ambiguous if several
    branches interrupted at once) — here there is exactly one interrupt
    node (review_slice), reached only after every parallel phase has fully
    joined.

    HITL invariant, same as build_agent_graph: only commit_slice and
    commit_relationships receive the write services (entity_service/
    edge_service) — no other node can reach canon.
    """
    builder: StateGraph[ImportState] = StateGraph(ImportState)

    builder.add_node("plan_windows", partial(plan_windows, source_store=source_store))
    builder.add_node(
        "build_registry",
        partial(
            build_registry,
            extraction=extraction,
            entity_store=entity_store,
            event_bus=event_bus,
        ),
    )
    builder.add_node(
        "extract_windows",
        partial(extract_windows, creative=creative, event_bus=event_bus),
    )
    builder.add_node(
        "merge_extractions", partial(merge_extractions, entity_store=entity_store)
    )
    builder.add_node("paginate_review", paginate_review)
    builder.add_node("review_slice", review_slice)
    builder.add_node(
        "commit_slice", partial(commit_slice, entity_service=entity_service)
    )
    builder.add_node("advance_slice", advance_slice)
    builder.add_node(
        "commit_relationships", partial(commit_relationships, edge_service=edge_service)
    )

    builder.add_edge(START, "plan_windows")
    builder.add_edge("plan_windows", "build_registry")
    builder.add_edge("build_registry", "extract_windows")
    builder.add_edge("extract_windows", "merge_extractions")
    builder.add_edge("merge_extractions", "paginate_review")
    builder.add_edge("paginate_review", "review_slice")
    builder.add_conditional_edges(
        "review_slice",
        route_after_slice_review,
        {"commit": "commit_slice", "skip": "advance_slice"},
    )
    builder.add_edge("commit_slice", "advance_slice")
    builder.add_conditional_edges(
        "advance_slice",
        route_after_advance,
        {
            "review": "review_slice",
            "commit": "commit_slice",
            "relationships": "commit_relationships",
        },
    )
    builder.add_edge("commit_relationships", END)

    return builder.compile(checkpointer=checkpointer)
