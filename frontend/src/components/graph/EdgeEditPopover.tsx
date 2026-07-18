import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Edge } from "../../api/types";
import { useEntity } from "../../hooks/useEntity";
import { useDeleteEdge, useUpdateEdge } from "../../hooks/useEdgesForEntity";
import { Icon } from "../ui/Icon";

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
  const { data: sourceEntity } = useEntity(projectId, edge.source_entity_id);
  const { data: targetEntity } = useEntity(projectId, edge.target_entity_id);
  const [edgeType, setEdgeType] = useState(edge.type);
  const [label, setLabel] = useState(edge.label ?? "");
  // Toggled locally; the actual swap only happens server-side on save, so
  // reopening the popover without saving leaves the edge untouched.
  const [reversed, setReversed] = useState(false);

  function handleSave() {
    if (!edgeType) return;
    updateEdge.mutate(
      { id: edge.id, data: { type: edgeType, label: label || null, reverse: reversed } },
      { onSuccess: onDone },
    );
  }

  function handleDelete() {
    deleteEdge.mutate(edge.id, { onSuccess: onDone });
  }

  const fromEntity = reversed ? targetEntity : sourceEntity;
  const toEntity = reversed ? sourceEntity : targetEntity;

  return (
    <div className="edge-popover">
      <h3>{t("edges.editRelationship")}</h3>
      <div className="edge-direction">
        <span className="edge-direction-entity" title={fromEntity?.title}>
          {fromEntity?.title ?? "…"}
        </span>
        <button
          type="button"
          className={`edge-direction-swap${reversed ? " is-reversed" : ""}`}
          onClick={() => setReversed((prev) => !prev)}
          title={t("edges.swapDirection")}
          aria-label={t("edges.swapDirection")}
        >
          <Icon name="swap" size={13} />
        </button>
        <span className="edge-direction-entity" title={toEntity?.title}>
          {toEntity?.title ?? "…"}
        </span>
      </div>
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
