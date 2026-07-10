import { useState } from "react";

import { useCreateEdge } from "../../hooks/useEdgesForEntity";

const SUGGESTED_EDGE_TYPES = ["contains", "ally_of", "family_of", "enemy_of"];

interface EdgeQuickFormProps {
  projectId: string;
  sourceId: string;
  targetId: string;
  onDone: () => void;
}

export function EdgeQuickForm({ projectId, sourceId, targetId, onDone }: EdgeQuickFormProps) {
  const createEdge = useCreateEdge(projectId);
  const [edgeType, setEdgeType] = useState("");
  const [label, setLabel] = useState("");

  function handleSubmit() {
    if (!edgeType) return;
    createEdge.mutate(
      { source_entity_id: sourceId, target_entity_id: targetId, type: edgeType, label: label || null },
      { onSuccess: onDone },
    );
  }

  return (
    <div className="edge-popover">
      <h3>New relationship</h3>
      <input
        list="edge-type-suggestions"
        placeholder="edge type (e.g. ally_of)"
        value={edgeType}
        onChange={(e) => setEdgeType(e.target.value)}
        autoFocus
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
      <div className="edge-popover-actions">
        <button type="button" onClick={handleSubmit} disabled={!edgeType || createEdge.isPending}>
          Create
        </button>
        <button type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
    </div>
  );
}
