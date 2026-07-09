import { useState } from "react";

import type { Edge } from "../../api/types";
import { useDeleteEdge, useUpdateEdge } from "../../hooks/useEdgesForEntity";

const SUGGESTED_EDGE_TYPES = ["contains", "ally_of", "family_of", "enemy_of"];

interface EdgeEditPopoverProps {
  edge: Edge;
  onDone: () => void;
}

export function EdgeEditPopover({ edge, onDone }: EdgeEditPopoverProps) {
  const updateEdge = useUpdateEdge();
  const deleteEdge = useDeleteEdge();
  const [edgeType, setEdgeType] = useState(edge.type);
  const [label, setLabel] = useState(edge.label ?? "");

  function handleSave() {
    if (!edgeType) return;
    updateEdge.mutate(
      { id: edge.id, data: { type: edgeType, label: label || null } },
      { onSuccess: onDone },
    );
  }

  function handleDelete() {
    deleteEdge.mutate(edge.id, { onSuccess: onDone });
  }

  return (
    <div className="edge-popover">
      <h3>Edit relationship</h3>
      <input
        list="edge-type-suggestions"
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
        <button type="button" onClick={handleSave} disabled={!edgeType || updateEdge.isPending}>
          Save
        </button>
        <button type="button" className="button-danger" onClick={handleDelete} disabled={deleteEdge.isPending}>
          Delete
        </button>
        <button type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
    </div>
  );
}
