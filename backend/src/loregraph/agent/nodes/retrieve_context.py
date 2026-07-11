import asyncio
from typing import Any

from loregraph.agent.state import NO_LORE_SENTINEL, AgentState
from loregraph.schemas.entity import EntityOut
from loregraph.schemas.graph import SubgraphOut
from loregraph.services.graph_query import get_subgraph
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.protocols import EdgeStore, EntityStore

RETRIEVAL_K = 6
ANCHOR_SUBGRAPH_DEPTH = 2
LORE_TEXT_LIMIT = 600  # chars per entity in the prompt — context, not a dump


async def retrieve_context(
    state: AgentState,
    *,
    vector_index: VectorIndex | None,
    entity_store: EntityStore,
    edge_store: EdgeStore,
) -> dict[str, Any]:
    """Hybrid retrieval: vector similarity + graph neighborhood, in parallel.

    Grounding is mandatory — generation never runs before this node, and an
    empty result is stated explicitly via NO_LORE_SENTINEL rather than left
    for the model to fill with guesses."""
    subgraph: SubgraphOut | None = None
    chunk_ids: list[str] = []

    async with asyncio.TaskGroup() as tg:
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
    if vector_task is not None:
        chunk_ids = [chunk.entity_id for chunk in vector_task.result()]
    if subgraph_task is not None:
        subgraph = subgraph_task.result()

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
    if subgraph is not None:
        lore_lines.extend(
            f'<relationship source="graph_store">'
            f"{edge.source_entity_id} --{edge.type}--> {edge.target_entity_id}"
            f"{f' ({edge.label})' if edge.label else ''}</relationship>"
            for edge in subgraph.edges
        )

    return {
        "existing_lore": "\n".join(lore_lines) if lore_lines else NO_LORE_SENTINEL,
        "context_entity_ids": context_ids,
        "known_entity_types": known_types,
    }


def _entity_line(entity: EntityOut) -> str:
    text = entity_to_text(entity)
    if len(text) > LORE_TEXT_LIMIT:
        text = text[:LORE_TEXT_LIMIT] + "…"
    return f'<entity id="{entity.id}" type="{entity.type}">{text}</entity>'
