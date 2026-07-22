import asyncio
import logging
from typing import Any

from loregraph.agent.state import NO_LORE_SENTINEL, AgentState
from loregraph.connectors.live import LiveSourceEntry, LiveSourceProvider
from loregraph.connectors.protocols import ExternalChunk
from loregraph.schemas.edge import EdgeOut
from loregraph.schemas.entity import EntityOut
from loregraph.schemas.graph import SubgraphOut
from loregraph.services.graph_query import edges_among, get_subgraph
from loregraph.services.knowledge_index import KB_RETRIEVAL_K, KnowledgeIndex
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.protocols import EdgeStore, EntityStore
from loregraph.storage.vectorstore.protocols import RetrievedChunk

logger = logging.getLogger(__name__)

RETRIEVAL_K = 6
ANCHOR_SUBGRAPH_DEPTH = 2
LORE_TEXT_LIMIT = 600  # chars per entity in the prompt — context, not a dump
# Relationships between retrieved entities are cheap per line but a dense
# graph can produce far more of them than entities. Truncation is stated in
# the prompt rather than silent: the model must not read a partial list as
# "these two are unconnected".
MAX_CONTEXT_EDGES = 40
KB_TEXT_LIMIT = 800  # chars per chunk — reference material, not a full dump
# External live sources (Foundry, LSS…) contribute grounding on a strict
# budget: they are optional flavor, never a reason to stall or fail a run.
EXTERNAL_GROUNDING_TIMEOUT_S = 8.0
EXTERNAL_GROUNDING_TEXT_LIMIT = 800
EXTERNAL_GROUNDING_CHUNKS_PER_SOURCE = 4
EXTERNAL_GROUNDING_SOURCE_LIMIT = 2

# Told explicitly instead of an empty block, same rationale as NO_LORE_SENTINEL:
# the model must not assume silence means "nothing was uploaded, invent freely".
NO_KNOWLEDGE_SENTINEL = (
    "(no knowledge-base documents are relevant to this request — either none "
    "were uploaded for this project, or embeddings are disabled)"
)


async def retrieve_context(
    state: AgentState,
    *,
    vector_index: VectorIndex | None,
    knowledge_index: KnowledgeIndex | None,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    live_sources: LiveSourceProvider | None = None,
) -> dict[str, Any]:
    """Hybrid retrieval: vector similarity + graph neighborhood + knowledge
    base, in parallel.

    Grounding is mandatory — generation never runs before this node, and an
    empty result is stated explicitly via NO_LORE_SENTINEL/NO_KNOWLEDGE_
    SENTINEL rather than left for the model to fill with guesses. The
    knowledge base is a separate contour from existing_lore/context_entity_
    ids on purpose: its chunks are reference material, never a valid
    grounded_in target (see prompts/generate_lore.system.md)."""
    subgraph: SubgraphOut | None = None
    chunk_ids: list[str] = []
    kb_chunks: list[RetrievedChunk] = []
    grounding_sources = (
        live_sources.grounding_entries()[:EXTERNAL_GROUNDING_SOURCE_LIMIT]
        if live_sources is not None
        else []
    )

    async with asyncio.TaskGroup() as tg:
        # External tasks are individually shielded (_query_external_safely
        # swallows everything but cancellation): a TaskGroup cancels siblings
        # on failure, and an offline Foundry must never take the vector/graph
        # retrieval down with it.
        external_tasks = [
            tg.create_task(_query_external_safely(entry, state.pending_brief))
            for entry in grounding_sources
        ]
        vector_task = (
            tg.create_task(
                vector_index.query(state.project_id, state.pending_brief, k=RETRIEVAL_K)
            )
            if vector_index is not None
            else None
        )
        subgraph_task = (
            tg.create_task(
                get_subgraph(
                    entity_store,
                    edge_store,
                    state.project_id,
                    state.anchor_entity_id,
                    depth=ANCHOR_SUBGRAPH_DEPTH,
                )
            )
            if state.anchor_entity_id is not None
            else None
        )
        knowledge_task = (
            tg.create_task(
                knowledge_index.query(
                    state.project_id, state.pending_brief, k=KB_RETRIEVAL_K
                )
            )
            if knowledge_index is not None
            else None
        )
    if vector_task is not None:
        chunk_ids = [chunk.entity_id for chunk in vector_task.result()]
    if subgraph_task is not None:
        subgraph = subgraph_task.result()
    if knowledge_task is not None:
        kb_chunks = knowledge_task.result()
    external_chunks = [chunk for task in external_tasks for chunk in task.result()]

    context_ids: list[str] = list(
        dict.fromkeys(
            chunk_ids + ([node.id for node in subgraph.nodes] if subgraph else [])
        )
    )
    entities = await entity_store.get_many(context_ids)
    lore_lines = [_entity_line(entity) for entity in entities]
    # Types already used in this project steer the model toward a consistent
    # taxonomy instead of inventing a new type name per run.
    all_entities = await entity_store.list_entities(state.project_id)
    known_types = sorted({entity.type for entity in all_entities})
    # Compact title→id map from retrieved entities only — bounded by
    # RETRIEVAL_K, enough for the LLM to create valid [[wikilinks]].
    # Full entity list is NOT dumped into the prompt (token-efficient).
    available_links = "\n".join(f"{entity.title} → {entity.id}" for entity in entities)

    # How the retrieved entities already connect. Deliberately not limited to
    # the anchor subgraph: with vector-only retrieval that branch is None and
    # the model used to see no relationships at all, which is exactly when it
    # guesses at connections that already exist. Runs after the TaskGroup
    # because entity_store and edge_store share one AsyncSession.
    title_by_id = {entity.id: entity.title for entity in entities}
    context_edges = list(
        {
            edge.id: edge
            for edge in [
                *(subgraph.edges if subgraph is not None else []),
                *await edges_among(edge_store, state.project_id, context_ids),
            ]
        }.values()
    )
    shown_edges = context_edges[:MAX_CONTEXT_EDGES]
    lore_lines.extend(_relationship_line(edge, title_by_id) for edge in shown_edges)
    if len(context_edges) > len(shown_edges):
        lore_lines.append(
            f"<!-- {len(context_edges) - len(shown_edges)} further relationships "
            f"between these entities exist but are not shown -->"
        )

    kb_lines = [_kb_chunk_line(chunk) for chunk in kb_chunks]
    # External chunks travel in the knowledge_context contour: same semantics
    # as kb_chunks (reference material, never a grounded_in target) and no
    # new AgentState field — persisted checkpoints stay compatible.
    kb_lines.extend(_external_chunk_line(chunk) for chunk in external_chunks)

    return {
        "existing_lore": "\n".join(lore_lines) if lore_lines else NO_LORE_SENTINEL,
        "knowledge_context": (
            "\n".join(kb_lines) if kb_lines else NO_KNOWLEDGE_SENTINEL
        ),
        "context_entity_ids": context_ids,
        "context_edge_ids": [edge.id for edge in shown_edges],
        "known_entity_types": known_types,
        "available_links": available_links,
    }


def _relationship_line(edge: EdgeOut, title_by_id: dict[str, str]) -> str:
    """One existing relationship, addressable by id.

    The id is what makes an existing relationship editable at all: an update
    or delete op has to name the edge it acts on, and this line is the only
    place the model ever learns that id. Titles ride along so it does not have
    to resolve opaque ids against the entity lines to understand the graph."""
    source = title_by_id.get(edge.source_entity_id, edge.source_entity_id)
    target = title_by_id.get(edge.target_entity_id, edge.target_entity_id)
    label = f" ({edge.label})" if edge.label else ""
    return (
        f'<relationship id="{edge.id}" source="graph_store">'
        f"{edge.source_entity_id} ({source}) --{edge.type}--> "
        f"{edge.target_entity_id} ({target}){label}</relationship>"
    )


def _entity_line(entity: EntityOut) -> str:
    text = entity_to_text(entity)
    if len(text) > LORE_TEXT_LIMIT:
        text = text[:LORE_TEXT_LIMIT] + "…"
    return f'<entity id="{entity.id}" type="{entity.type}">{text}</entity>'


def _kb_chunk_line(chunk: RetrievedChunk) -> str:
    text = chunk.text
    if len(text) > KB_TEXT_LIMIT:
        text = text[:KB_TEXT_LIMIT] + "…"
    return f'<kb_chunk source="{chunk.entity_id}">{text}</kb_chunk>'


async def _query_external_safely(
    entry: LiveSourceEntry, brief: str
) -> list[ExternalChunk]:
    """Generation must never fail (or hang) because Foundry is off:
    everything except cancellation degrades to a warning and no chunks."""
    try:
        async with asyncio.timeout(EXTERNAL_GROUNDING_TIMEOUT_S):
            chunks = await entry.source.query(brief)
        return chunks[:EXTERNAL_GROUNDING_CHUNKS_PER_SOURCE]
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning(
            "External grounding source %s unavailable; generation proceeds without it.",
            entry.name,
            exc_info=True,
        )
        return []


def _external_chunk_line(chunk: ExternalChunk) -> str:
    text = chunk.text
    if len(text) > EXTERNAL_GROUNDING_TEXT_LIMIT:
        text = text[:EXTERNAL_GROUNDING_TEXT_LIMIT] + "…"
    return (
        f'<external_source name="{chunk.source_name}" '
        f'type="{chunk.connector_type}" kind="{chunk.kind}">'
        f"{chunk.title}: {text}</external_source>"
    )
