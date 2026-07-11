from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from loregraph.agent.state import AgentState
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.protocols import EntityStore

SEARCH_K = 5
# Tool outputs are prompt input on the next assistant call — keep them tight.
DETAIL_TEXT_LIMIT = 800
SEARCH_TEXT_LIMIT = 200


async def run_tools(
    state: AgentState,
    *,
    vector_index: VectorIndex | None,
    entity_store: EntityStore,
) -> dict[str, Any]:
    """Executes the assistant's read tools against the project's stores.

    A custom executor (not a prebuilt ToolNode) so the tools go through the
    same injected abstractions as everything else and tests can fake them."""
    last = state.messages[-1]
    assert isinstance(last, AIMessage)
    results: list[ToolMessage] = []
    for call in last.tool_calls:
        match call["name"]:
            case "search_lore":
                content = await _search_lore(
                    vector_index,
                    entity_store,
                    state.project_id,
                    str(call["args"].get("query", "")),
                )
            case "get_entity_details":
                content = await _entity_details(
                    entity_store,
                    state.project_id,
                    str(call["args"].get("entity_id", "")),
                )
            case unknown:
                content = f"Unknown tool: {unknown}"
        results.append(ToolMessage(content, tool_call_id=call["id"] or ""))
    return {"messages": results}


async def _search_lore(
    vector_index: VectorIndex | None,
    entity_store: EntityStore,
    project_id: str,
    query: str,
) -> str:
    if vector_index is None:
        # Degrade to title substring match — the assistant stays usable
        # with embeddings disabled, just less clever.
        entities = await entity_store.list_entities(project_id)
        needle = query.casefold()
        hits = [e for e in entities if needle in e.title.casefold()][:SEARCH_K]
        if not hits:
            return "No lore found for this query."
        return "\n".join(f"{e.id} | {e.type} | {e.title}" for e in hits)
    chunks = await vector_index.query(project_id, query, k=SEARCH_K)
    if not chunks:
        return "No lore found for this query."
    entities = await entity_store.get_many([chunk.entity_id for chunk in chunks])
    titles = {entity.id: entity for entity in entities}
    lines = []
    for chunk in chunks:
        entity = titles.get(chunk.entity_id)
        head = (
            f"{chunk.entity_id} | {entity.type} | {entity.title}"
            if entity
            else chunk.entity_id
        )
        lines.append(f"{head} — {chunk.text[:SEARCH_TEXT_LIMIT]}")
    return "\n".join(lines)


async def _entity_details(
    entity_store: EntityStore, project_id: str, entity_id: str
) -> str:
    entities = await entity_store.get_many([entity_id])
    if not entities or entities[0].project_id != project_id:
        return f"Entity not found: {entity_id}"
    return entity_to_text(entities[0])[:DETAIL_TEXT_LIMIT]
