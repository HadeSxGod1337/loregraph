from collections import defaultdict, deque

from loregraph.exceptions import EntityNotFoundError
from loregraph.schemas.graph import SubgraphOut
from loregraph.storage.protocols import EdgeStore, EntityStore


async def get_subgraph(
    entity_store: EntityStore,
    edge_store: EdgeStore,
    root_id: str,
    depth: int,
    edge_types: frozenset[str] | None = None,
) -> SubgraphOut:
    """BFS over an undirected view of the edge graph, rooted at root_id.

    Undirected on purpose: a `contains` edge stored City->Tavern should still
    surface City when viewing the neighborhood from Tavern's side.

    Node lookups are one batched `get_many` call rather than N concurrent
    `get` calls: entity_store and edge_store share a single AsyncSession for
    this request, and SQLAlchemy's AsyncSession does not support concurrent
    use by multiple coroutines.
    """
    if not await entity_store.exists(root_id):
        raise EntityNotFoundError(root_id)

    edges = await edge_store.list_all(edge_types)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source_entity_id].append(edge.target_entity_id)
        adjacency[edge.target_entity_id].append(edge.source_entity_id)

    distances: dict[str, int] = {root_id: 0}
    queue: deque[str] = deque([root_id])
    while queue:
        current = queue.popleft()
        current_depth = distances[current]
        if current_depth >= depth:
            continue
        for neighbor_id in adjacency[current]:
            if neighbor_id not in distances:
                distances[neighbor_id] = current_depth + 1
                queue.append(neighbor_id)

    included_edges = [
        edge
        for edge in edges
        if edge.source_entity_id in distances and edge.target_entity_id in distances
    ]
    nodes = await entity_store.get_many(list(distances))
    return SubgraphOut(nodes=nodes, edges=included_edges)
