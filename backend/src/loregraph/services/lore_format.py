"""Shared rendering of graph relationships for anything an LLM reads.

Three call sites now render the same edge: the proposal pipeline's retrieved
context (agent/nodes/retrieve_context.py), the relationship skill's "what
already connects these" block (agent/nodes/generate_relationships.py) and the
assistant's read tools (agent/nodes/tools.py). That is the third occurrence
CLAUDE.md's DRY rule waits for, and the format is not cosmetic: the `id`
attribute is the only place a model ever learns which edge an update/delete
op would act on, so a drifting copy silently costs the model that ability.

Pure functions, no I/O — the callers own the fetching.
"""

from collections.abc import Mapping

from loregraph.schemas.edge import EdgeOut


def relationship_line(
    edge: EdgeOut,
    title_by_id: Mapping[str, str],
    *,
    with_endpoint_ids: bool = True,
    source: str | None = "graph_store",
) -> str:
    """One existing relationship, addressable by id.

    Titles ride along so the model does not have to resolve opaque ids
    against the entity lines to understand the graph.

    `with_endpoint_ids` adds each end's id next to its title — needed
    wherever the model may act on the endpoints (retrieval context, chat
    tools), pointless where the ids were already listed separately.
    `source` fills the provenance attribute; None omits it.
    """
    source_attr = f' source="{source}"' if source else ""
    label = f" ({edge.label})" if edge.label else ""
    if with_endpoint_ids:
        ends = (
            f"{edge.source_entity_id} "
            f"({title_by_id.get(edge.source_entity_id, edge.source_entity_id)}) "
            f"--{edge.type}--> "
            f"{edge.target_entity_id} "
            f"({title_by_id.get(edge.target_entity_id, edge.target_entity_id)})"
        )
    else:
        ends = (
            f"{title_by_id.get(edge.source_entity_id, edge.source_entity_id)} "
            f"--{edge.type}--> "
            f"{title_by_id.get(edge.target_entity_id, edge.target_entity_id)}"
        )
    return f'<relationship id="{edge.id}"{source_attr}>{ends}{label}</relationship>'
