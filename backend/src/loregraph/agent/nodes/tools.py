import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from loregraph.agent.mcp_tools import McpToolProvider
from loregraph.agent.state import AgentState
from loregraph.connectors.live import LiveSourceProvider
from loregraph.exceptions import ConnectorError
from loregraph.services.knowledge_index import KB_RETRIEVAL_K, KnowledgeIndex
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.protocols import EntityStore

logger = logging.getLogger(__name__)

SEARCH_K = 5
# Tool outputs are prompt input on the next assistant call — keep them tight.
DETAIL_TEXT_LIMIT = 800
SEARCH_TEXT_LIMIT = 200
KB_SEARCH_TEXT_LIMIT = 400
EXTERNAL_TEXT_LIMIT = 400  # chars per external chunk
# A generic safety net across every LiveSource implementation (Foundry,
# LongStoryShort, future connectors) against a misbehaving connector
# returning an unbounded response — NOT the primary budget control anymore.
# Each connector now applies its own kind-aware budget internally (see e.g.
# FoundryConnector.query()'s per-branch _*_CHUNK_LIMIT constants); this only
# needs to be generous enough not to undo that. Sized for the largest
# legitimate combined case (Foundry's kind=None fan-out: 5 journal + 30
# actor + 30 item = 65).
EXTERNAL_CHUNK_LIMIT = 65
EXTERNAL_QUERY_TIMEOUT_S = 12.0


async def run_tools(
    state: AgentState,
    *,
    vector_index: VectorIndex | None,
    knowledge_index: KnowledgeIndex | None,
    entity_store: EntityStore,
    live_sources: LiveSourceProvider | None = None,
    mcp_tools: McpToolProvider | None = None,
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
            case "search_knowledge_base":
                content = await _search_knowledge_base(
                    knowledge_index,
                    state.project_id,
                    str(call["args"].get("query", "")),
                )
            case "query_external_source":
                kind = call["args"].get("kind")
                content = await _query_external_source(
                    live_sources,
                    str(call["args"].get("source", "")),
                    str(call["args"].get("query", "")),
                    str(kind) if isinstance(kind, str) and kind else None,
                )
            case name if name.startswith("mcp__"):
                content = await _call_mcp_tool(mcp_tools, name, dict(call["args"]))
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


async def _query_external_source(
    live_sources: LiveSourceProvider | None,
    source_name: str,
    query: str,
    kind: str | None,
) -> str:
    """Never raises: an offline Foundry must produce a readable tool message
    the assistant can relay, not an exception out of the node."""
    if live_sources is None:
        return "No external sources are connected to this project."
    entry = live_sources.get(source_name)
    if entry is None:
        names = ", ".join(live_sources.names())
        return f"Unknown external source: {source_name!r}. Available: {names}"
    try:
        async with asyncio.timeout(EXTERNAL_QUERY_TIMEOUT_S):
            chunks = await entry.source.query(query, kind=kind)
    except asyncio.CancelledError:
        raise
    except (ConnectorError, TimeoutError) as e:
        logger.warning(
            "External source %s unavailable during chat query",
            entry.name,
            exc_info=True,
        )
        return (
            f"External source '{entry.name}' is unavailable right now "
            f"({type(e).__name__}). Tell the game master it may be offline."
        )
    if not chunks:
        return f"'{entry.name}' returned nothing for this query."
    shown = chunks[:EXTERNAL_CHUNK_LIMIT]
    lines = [
        f"[{chunk.kind}] {chunk.title}: {chunk.text[:EXTERNAL_TEXT_LIMIT]}"
        for chunk in shown
    ]
    # Truncation must be visible, never silent — otherwise a partial list
    # gets relayed to the game master as if it were complete (exactly the
    # bug this is fixing: "add all items" quietly returning 5 of 11 with no
    # indication anything was cut).
    if len(chunks) > len(shown):
        lines.append(
            f"(showing {len(shown)} of {len(chunks)} results — narrow the "
            "query if you need the rest.)"
        )
    return "\n".join(lines)


async def _call_mcp_tool(
    mcp_tools: McpToolProvider | None,
    qualified_name: str,
    arguments: dict[str, Any],
) -> str:
    """Never raises: a generic MCP server going offline mid-turn must
    produce a readable tool message, not an exception out of the node —
    same graceful-degradation contract as _query_external_source."""
    if mcp_tools is None:
        return "No MCP tool sources are connected to this project."
    entry = mcp_tools.get(qualified_name)
    if entry is None:
        return f"Unknown MCP tool: {qualified_name!r}."
    try:
        async with asyncio.timeout(EXTERNAL_QUERY_TIMEOUT_S):
            return await entry.source.call_mcp_tool(entry.tool.name, arguments)
    except asyncio.CancelledError:
        raise
    except (ConnectorError, TimeoutError) as e:
        logger.warning(
            "MCP connection %s unavailable during a tool call",
            entry.connection_name,
            exc_info=True,
        )
        return (
            f"MCP connection '{entry.connection_name}' is unavailable right "
            f"now ({type(e).__name__}). Tell the game master it may be offline."
        )


async def _search_knowledge_base(
    knowledge_index: KnowledgeIndex | None, project_id: str, query: str
) -> str:
    if knowledge_index is None:
        return (
            "Knowledge base search is unavailable (embeddings are disabled "
            "for this deployment)."
        )
    chunks = await knowledge_index.query(project_id, query, k=KB_RETRIEVAL_K)
    if not chunks:
        return "No knowledge base documents matched this query."
    return "\n".join(chunk.text[:KB_SEARCH_TEXT_LIMIT] for chunk in chunks)
