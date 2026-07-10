import { useState } from "react";

import { useEntities } from "../../hooks/useEntities";
import { useCreateEdge } from "../../hooks/useEdgesForEntity";

const SUGGESTED_EDGE_TYPES = ["contains", "ally_of", "family_of", "enemy_of"];

export function EdgeForm({ projectId, entityId }: { projectId: string; entityId: string }) {
  const { data: entities } = useEntities(projectId);
  const createEdge = useCreateEdge(projectId);

  const [targetId, setTargetId] = useState("");
  const [edgeType, setEdgeType] = useState("");
  const [label, setLabel] = useState("");

  const otherEntities = entities?.filter((e) => e.id !== entityId) ?? [];

  function handleSubmit() {
    if (!targetId || !edgeType) return;
    createEdge.mutate(
      {
        source_entity_id: entityId,
        target_entity_id: targetId,
        type: edgeType,
        label: label || null,
      },
      {
        onSuccess: () => {
          setTargetId("");
          setEdgeType("");
          setLabel("");
        },
      },
    );
  }

  return (
    <div className="edge-form">
      <select value={targetId} onChange={(e) => setTargetId(e.target.value)}>
        <option value="">— link to entity —</option>
        {otherEntities.map((e) => (
          <option key={e.id} value={e.id}>
            {e.title} ({e.type})
          </option>
        ))}
      </select>

      <input
        list="edge-type-suggestions"
        placeholder="edge type (e.g. ally_of)"
        value={edgeType}
        onChange={(e) => setEdgeType(e.target.value)}
      />
      <datalist id="edge-type-suggestions">
        {SUGGESTED_EDGE_TYPES.map((t) => (
          <option key={t} value={t} />
        ))}
      </datalist>

      <input
        placeholder="reason / label (optional)"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
      />

      <button type="button" onClick={handleSubmit} disabled={createEdge.isPending}>
        Add relationship
      </button>
    </div>
  );
}
