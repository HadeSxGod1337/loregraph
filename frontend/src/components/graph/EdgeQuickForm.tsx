import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useCreateEdge } from "../../hooks/useEdgesForEntity";

const SUGGESTED_EDGE_TYPES = ["contains", "ally_of", "family_of", "enemy_of"];

interface EdgeQuickFormProps {
  projectId: string;
  sourceId: string;
  targetId: string;
  onDone: () => void;
}

export function EdgeQuickForm({ projectId, sourceId, targetId, onDone }: EdgeQuickFormProps) {
  const { t } = useTranslation();
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
      <h3>{t("edges.newRelationship")}</h3>
      <input
        list="edge-type-suggestions"
        placeholder={t("edges.edgeTypePlaceholder")}
        value={edgeType}
        onChange={(e) => setEdgeType(e.target.value)}
        autoFocus
      />
      <datalist id="edge-type-suggestions">
        {SUGGESTED_EDGE_TYPES.map((suggestion) => (
          <option key={suggestion} value={suggestion} />
        ))}
      </datalist>
      <input
        placeholder={t("edges.reasonPlaceholder")}
        value={label}
        onChange={(e) => setLabel(e.target.value)}
      />
      <div className="edge-popover-actions">
        <button type="button" onClick={handleSubmit} disabled={!edgeType || createEdge.isPending}>
          {t("common.create")}
        </button>
        <button type="button" onClick={onDone}>
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}
