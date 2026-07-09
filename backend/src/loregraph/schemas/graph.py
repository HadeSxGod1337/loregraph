from pydantic import BaseModel

from loregraph.schemas.edge import EdgeOut
from loregraph.schemas.entity import EntityOut


class SubgraphOut(BaseModel):
    nodes: list[EntityOut]
    edges: list[EdgeOut]
