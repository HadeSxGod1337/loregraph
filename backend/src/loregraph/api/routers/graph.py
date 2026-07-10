from typing import Annotated

from fastapi import APIRouter, Query

from loregraph.api.deps import EdgeStoreDep, EntityStoreDep
from loregraph.schemas.graph import SubgraphOut
from loregraph.services.graph_query import get_subgraph

router = APIRouter(prefix="/projects/{project_id}/graph", tags=["graph"])


@router.get("/subgraph", response_model=SubgraphOut)
async def subgraph(
    project_id: str,
    entity_store: EntityStoreDep,
    edge_store: EdgeStoreDep,
    root_id: str,
    depth: Annotated[int, Query(ge=0, le=10)] = 1,
    edge_type: Annotated[list[str] | None, Query()] = None,
) -> SubgraphOut:
    edge_types = frozenset(edge_type) if edge_type else None
    return await get_subgraph(
        entity_store, edge_store, project_id, root_id, depth, edge_types
    )
