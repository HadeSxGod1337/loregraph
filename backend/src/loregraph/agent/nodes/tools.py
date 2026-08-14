import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from loregraph.agent.mcp_tools import McpToolProvider
from loregraph.agent.skills.registry import (
    GRAPH_DEPTH_MAX,
    LIST_ENTITIES_LIMIT,
    SEARCH_K_DEFAULT,
    SEARCH_K_MAX,
)
from loregraph.agent.state import AgentState
from loregraph.connectors.live import LiveSourceProvider
from loregraph.exceptions import ConnectorError, EntityNotFoundError
from loregraph.schemas.edge import EdgeOut
from loregraph.schemas.entity import EntityOut
from loregraph.services.graph_query import get_subgraph
from loregraph.services.knowledge_index import KB_RETRIEVAL_K, KnowledgeIndex
from loregraph.services.lore_format import relationship_line
from loregraph.services.lore_search import search_lore
from loregraph.services.vector_index import VectorIndex, entity_to_text
from loregraph.storage.protocols import EdgeStore, EntityStore

logger = logging.getLogger(__name__)

# Tool outputs are prompt input on the next assistant call — keep them tight.
DETAIL_TEXT_LIMIT = 1500
SEARCH_TEXT_LIMIT = 200
# Relationship budgets, mirroring retrieve_context's MAX_CONTEXT_EDGES: cheap
# per line, but a hub entity in a dense campaign has enough of them to drown
# out everything else in the tool result.
DETAIL_MAX_EDGES = 40
GRAPH_MAX_EDGES = 60
GRAPH_MAX_NODES = 60
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
# How many matched MCP tools discover_mcp_tools returns WITH their full input
# schema. A broad query can match many tools; past this we list the rest by
# name only so the discovery result itself never blows up the prompt.
MCP_DISCOVER_SCHEMA_LIMIT = 8


async def run_tools(
    state: AgentState,
    *,
    vector_index: VectorIndex | None,
    knowledge_index: KnowledgeIndex | None,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    live_sources: LiveSourceProvider | None = None,
    mcp_tools: McpToolProvider | None = None,
) -> dict[str, Any]:
    """Executes the assistant's read tools against the project's stores.

    A custom executor (not a prebuilt ToolNode) so the tools go through the
    same injected abstractions as everything else and tests can fake them.

    `edge_store` is the read protocol, never EdgeService: this node has no
    write access by design (the HITL invariant), it only has to be able to
    *see* the graph — which until now it could not, so the assistant denied
    relationships that plainly existed.
    """
    last = state.messages[-1]
    assert isinstance(last, AIMessage)
    results: list[ToolMessage] = []
    for call in last.tool_calls:
        match call["name"]:
            case "search_lore":
                content = await _search_lore(
                    vector_index,
                    entity_store,
                    edge_store,
                    state.project_id,
                    str(call["args"].get("query", "")),
                    entity_type=_optional_str(call["args"].get("entity_type")),
                    limit=_optional_int(call["args"].get("limit")),
                )
            case "get_entity_details":
                content = await _entity_details(
                    entity_store,
                    edge_store,
                    state.project_id,
                    str(call["args"].get("entity_id", "")),
                )
            case "list_entities":
                content = await _list_entities(
                    entity_store,
                    state.project_id,
                    entity_type=_optional_str(call["args"].get("entity_type")),
                    title_contains=_optional_str(call["args"].get("title_contains")),
                )
            case "get_entity_graph":
                content = await _entity_graph(
                    entity_store,
                    edge_store,
                    state.project_id,
                    str(call["args"].get("entity_id", "")),
                    _optional_int(call["args"].get("depth")) or 1,
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
            case "discover_mcp_tools":
                content = await _discover_mcp_tools(
                    mcp_tools, str(call["args"].get("query", ""))
                )
            case "call_mcp_tool":
                raw_args = call["args"].get("arguments")
                content = await _call_mcp_tool(
                    mcp_tools,
                    str(call["args"].get("tool", "")),
                    dict(raw_args) if isinstance(raw_args, dict) else {},
                )
            case unknown:
                content = f"Unknown tool: {unknown}"
        results.append(ToolMessage(content, tool_call_id=call["id"] or ""))
    return {"messages": results}


def _optional_str(value: Any) -> str | None:
    """Tool arguments arrive as whatever the model emitted — an absent filter
    and an empty string both mean "no filter", never a literal match on ""."""
    return value.strip() or None if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):  # bool is an int subclass; never a count
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _entity_head(entity: EntityOut) -> str:
    return f"{entity.id} | {entity.type} | {entity.title}"


def _truncation_note(shown: int, total: int, hint: str) -> str | None:
    """Truncation must be visible, never silent — a capped list read as a
    complete one is how the assistant ends up miscounting the world."""
    if shown >= total:
        return None
    return f"(showing {shown} of {total} — {hint})"


def _edge_summary(edges: list[EdgeOut], entity_id: str) -> str:
    """Compact census of one entity's relationships, e.g. `ally_of ×3,
    enemy_of ×1`. Enough for the model to notice there is a graph worth
    opening with get_entity_graph, without printing it inside every search
    result."""
    counts: dict[str, int] = {}
    for edge in edges:
        if entity_id in (edge.source_entity_id, edge.target_entity_id):
            counts[edge.type] = counts.get(edge.type, 0) + 1
    if not counts:
        return "no relationships"
    return ", ".join(
        f"{edge_type} ×{count}" for edge_type, count in sorted(counts.items())
    )


async def _search_lore(
    vector_index: VectorIndex | None,
    entity_store: EntityStore,
    edge_store: EdgeStore,
    project_id: str,
    query: str,
    *,
    entity_type: str | None = None,
    limit: int | None = None,
) -> str:
    """Formatting only — the ranking itself lives in services/lore_search.py,
    where it can be unit-tested without a graph, a model or a tool call."""
    k = SEARCH_K_DEFAULT if limit is None or limit <= 0 else min(limit, SEARCH_K_MAX)
    result = await search_lore(
        vector_index=vector_index,
        entity_store=entity_store,
        project_id=project_id,
        query=query,
        limit=k,
        entity_type=entity_type,
    )
    if not result.entities:
        return (
            "No lore found for this query. Try different wording, a bare "
            "proper name, or list_entities to check what exists at all."
        )
    edges = await edge_store.list_all(project_id)
    lines = [
        f"{_entity_head(entity)} — {entity_to_text(entity)[:SEARCH_TEXT_LIMIT]} "
        f"[{_edge_summary(edges, entity.id)}]"
        for entity in result.entities
    ]
    note = _truncation_note(
        len(result.entities),
        result.total,
        "best matches only; this is never a complete list",
    )
    if note:
        lines.append(note)
    return "\n".join(lines)


async def _entity_details(
    entity_store: EntityStore,
    edge_store: EdgeStore,
    project_id: str,
    entity_id: str,
) -> str:
    """Fields AND relationships.

    Relationships are stored outside the entity (EdgeStore), so a details
    view built only from entity_to_text reports a connected entity as having
    none — which is exactly what the assistant used to tell game masters
    while the graph showed the edge.
    """
    entities = await entity_store.get_many([entity_id])
    if not entities or entities[0].project_id != project_id:
        return f"Entity not found: {entity_id}"
    entity = entities[0]
    lines = [entity_to_text(entity)[:DETAIL_TEXT_LIMIT]]

    edges = await edge_store.list_for_entity(entity_id)
    if not edges:
        lines.append("\nrelationships: none recorded in the graph.")
        return "\n".join(lines)
    shown = edges[:DETAIL_MAX_EDGES]
    title_by_id = await _titles_for_edges(entity_store, shown, entity)
    lines.append(f"\nrelationships ({len(edges)}):")
    lines.extend(relationship_line(edge, title_by_id) for edge in shown)
    note = _truncation_note(
        len(shown), len(edges), "use get_entity_graph for the full neighborhood"
    )
    if note:
        lines.append(note)
    return "\n".join(lines)


async def _titles_for_edges(
    entity_store: EntityStore, edges: list[EdgeOut], known: EntityOut
) -> dict[str, str]:
    """Neighbour titles in ONE batched get_many: entity_store and edge_store
    share a single AsyncSession per request, which SQLAlchemy forbids using
    from concurrent coroutines."""
    neighbour_ids = {
        end
        for edge in edges
        for end in (edge.source_entity_id, edge.target_entity_id)
        if end != known.id
    }
    neighbours = await entity_store.get_many(sorted(neighbour_ids))
    return {known.id: known.title} | {
        neighbour.id: neighbour.title for neighbour in neighbours
    }


async def _list_entities(
    entity_store: EntityStore,
    project_id: str,
    *,
    entity_type: str | None = None,
    title_contains: str | None = None,
) -> str:
    """Exhaustive enumeration with an exact count — the contour semantic
    search structurally cannot serve."""
    entities = await entity_store.list_entities(project_id, entity_type)
    if title_contains:
        needle = title_contains.casefold()
        entities = [e for e in entities if needle in e.title.casefold()]
    if not entities:
        return f"No entities match{_filter_suffix(entity_type, title_contains)}."

    shown = entities[:LIST_ENTITIES_LIMIT]
    header = (
        f"{len(entities)} entities match{_filter_suffix(entity_type, title_contains)}."
    )
    lines = [header]
    if entity_type is None:
        by_type: dict[str, int] = {}
        for entity in entities:
            by_type[entity.type] = by_type.get(entity.type, 0) + 1
        lines.append(
            "by type: "
            + ", ".join(f"{name} {count}" for name, count in sorted(by_type.items()))
        )
    lines.extend(_entity_head(entity) for entity in shown)
    note = _truncation_note(
        len(shown),
        len(entities),
        "the count above is exact; narrow with entity_type or title_contains "
        "to see the rest",
    )
    if note:
        lines.append(note)
    return "\n".join(lines)


def _filter_suffix(entity_type: str | None, title_contains: str | None) -> str:
    parts = []
    if entity_type:
        parts.append(f"type={entity_type!r}")
    if title_contains:
        parts.append(f"title contains {title_contains!r}")
    return f" ({', '.join(parts)})" if parts else " in this world"


async def _entity_graph(
    entity_store: EntityStore,
    edge_store: EdgeStore,
    project_id: str,
    entity_id: str,
    depth: int,
) -> str:
    bounded_depth = max(1, min(depth, GRAPH_DEPTH_MAX))
    try:
        subgraph = await get_subgraph(
            entity_store, edge_store, project_id, entity_id, depth=bounded_depth
        )
    except EntityNotFoundError:
        return f"Entity not found: {entity_id}"
    if not subgraph.edges:
        return (
            f"{entity_id} has no relationships in the graph at depth {bounded_depth}."
        )
    title_by_id = {node.id: node.title for node in subgraph.nodes}
    shown_nodes = subgraph.nodes[:GRAPH_MAX_NODES]
    shown_edges = subgraph.edges[:GRAPH_MAX_EDGES]
    lines = [f"neighborhood of {entity_id} at depth {bounded_depth}:"]
    lines.extend(_entity_head(node) for node in shown_nodes)
    lines.extend(relationship_line(edge, title_by_id) for edge in shown_edges)
    for shown, total, hint in (
        (len(shown_nodes), len(subgraph.nodes), "entities"),
        (len(shown_edges), len(subgraph.edges), "relationships"),
    ):
        note = _truncation_note(shown, total, f"{hint}; lower the depth")
        if note:
            lines.append(note)
    return "\n".join(lines)


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


async def _discover_mcp_tools(mcp_tools: McpToolProvider | None, query: str) -> str:
    """Progressive disclosure: the model's entry point into any connected MCP
    server's tools. Returns matched tools' qualified name + description +
    real input schema (so the model can then call one), or the whole catalog
    by name when the query is empty. Never raises — an offline server yields
    a readable message, same graceful-degradation contract as the rest."""
    if mcp_tools is None:
        return "No MCP tool sources are connected to this project."
    try:
        async with asyncio.timeout(EXTERNAL_QUERY_TIMEOUT_S):
            matches = await mcp_tools.find(query)
    except asyncio.CancelledError:
        raise
    except (ConnectorError, TimeoutError) as e:
        logger.warning("MCP catalog unavailable during discovery", exc_info=True)
        return (
            f"Connected MCP servers are unavailable right now "
            f"({type(e).__name__}). Tell the game master they may be offline."
        )
    if not matches:
        return (
            f"No MCP tools matched {query!r}. Call discover_mcp_tools with an "
            "empty query to see everything available."
        )
    lines: list[str] = []
    for entry in matches[:MCP_DISCOVER_SCHEMA_LIMIT]:
        schema = json.dumps(entry.tool.input_schema or {}, ensure_ascii=False)
        lines.append(
            f"{entry.qualified_name}: {entry.tool.description}\n"
            f"  input schema: {schema}"
        )
    remainder = matches[MCP_DISCOVER_SCHEMA_LIMIT:]
    if remainder:
        names = ", ".join(entry.qualified_name for entry in remainder)
        lines.append(
            f"(more matches, names only — refine the query for their schemas: {names})"
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
    try:
        async with asyncio.timeout(EXTERNAL_QUERY_TIMEOUT_S):
            return await mcp_tools.call(qualified_name, arguments)
    except asyncio.CancelledError:
        raise
    except KeyError:
        return (
            f"Unknown MCP tool: {qualified_name!r}. Call discover_mcp_tools "
            "first to get an exact tool name."
        )
    except (ConnectorError, TimeoutError) as e:
        logger.warning(
            "MCP tool call %s failed (connection unavailable)",
            qualified_name,
            exc_info=True,
        )
        return (
            f"MCP tool {qualified_name!r} is unavailable right now "
            f"({type(e).__name__}). Tell the game master the server may be offline."
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
