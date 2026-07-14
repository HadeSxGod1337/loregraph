import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Edge } from "../../api/types";
import { useDeleteEdge, useUpdateEdge } from "../../hooks/useEdgesForEntity";

const SUGGESTED_EDGE_TYPES = ["contains", "ally_of", "family_of", "enemy_of"];

interface EdgeEditPopoverProps {
  projectId: string;
  edge: Edge;
  onDone: () => void;
}

export function EdgeEditPopover({ projectId, edge, onDone }: EdgeEditPopoverProps) {
  const { t } = useTranslation();
  const updateEdge = useUpdateEdge(projectId);
  const deleteEdge = useDeleteEdge(projectId);
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
      <h3>{t("edges.editRelationship")}</h3>
      <input
        list="edge-type-suggestions"
        value={edgeType}
        onChange={(e) => setEdgeType(e.target.value)}
        autoFocus
      />
      <datalist id="edge-type-suggestions">
        {SUGGESTED_EDGE_TYPES.map((suggestion) => (
          <option key={suggestion} value={suggestion} />
        ))}
      </datalist>
      <textarea
        placeholder={t("edges.reasonPlaceholder")}
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        rows={2}
      />
      <div className="edge-popover-actions">
        <button type="button" onClick={handleSave} disabled={!edgeType || updateEdge.isPending}>
          {t("common.save")}
        </button>
        <button type="button" className="button-danger" onClick={handleDelete} disabled={deleteEdge.isPending}>
          {t("common.delete")}
        </button>
        <button type="button" onClick={onDone}>
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}
