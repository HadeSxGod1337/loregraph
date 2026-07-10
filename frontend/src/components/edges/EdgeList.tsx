import { useEntities } from "../../hooks/useEntities";
import { useDeleteEdge, useEdgesForEntity } from "../../hooks/useEdgesForEntity";

export function EdgeList({ projectId, entityId }: { projectId: string; entityId: string }) {
  const { data: edges } = useEdgesForEntity(projectId, entityId);
  const { data: entities } = useEntities(projectId);
  const deleteEdge = useDeleteEdge(projectId);

  const titleFor = (id: string) => entities?.find((e) => e.id === id)?.title ?? id;

  return (
    <div className="edge-list">
      <h3>Relationships</h3>
      {edges?.length === 0 && <p>No relationships yet.</p>}
      <ul>
        {edges?.map((edge) => {
          const isOutgoing = edge.source_entity_id === entityId;
          const otherId = isOutgoing ? edge.target_entity_id : edge.source_entity_id;
          return (
            <li key={edge.id} className="edge-list-item">
              <span>{isOutgoing ? "→" : "←"}</span>
              <span className="edge-type-badge">{edge.type}</span>
              <span>{titleFor(otherId)}</span>
              {edge.label && <span className="edge-label">"{edge.label}"</span>}
              <button
                type="button"
                className="button-danger"
                onClick={() => deleteEdge.mutate(edge.id)}
                title="Remove this relationship"
              >
                Remove
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
