import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Edge } from "../../api/types";
import { useEntities } from "../../hooks/useEntities";
import { useDeleteEdge, useEdgesForEntity } from "../../hooks/useEdgesForEntity";
import { EdgeEditPopover } from "../graph/EdgeEditPopover";
import { Icon } from "../ui/Icon";

export function EdgeList({ projectId, entityId }: { projectId: string; entityId: string }) {
  const { t } = useTranslation();
  const { data: edges } = useEdgesForEntity(projectId, entityId);
  const { data: entities } = useEntities(projectId);
  const deleteEdge = useDeleteEdge(projectId);
  const [editingEdge, setEditingEdge] = useState<Edge | null>(null);

  const titleFor = (id: string) => entities?.find((e) => e.id === id)?.title ?? id;

  return (
    <div className="edge-list">
      <h3>{t("edges.relationshipsHeading")}</h3>
      {edges?.length === 0 && <p>{t("edges.noRelationships")}</p>}
      <ul>
        {edges?.map((edge) => {
          const isOutgoing = edge.source_entity_id === entityId;
          const otherId = isOutgoing ? edge.target_entity_id : edge.source_entity_id;
          return (
            <li key={edge.id} className="rel-row">
              <span className="rel-main">
                <span className="rel-arrow">{isOutgoing ? "→" : "←"}</span>
                <span className="rel-type">{edge.type}</span>
                <span className="rel-title">{titleFor(otherId)}</span>
              </span>
              <span className="rel-actions">
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setEditingEdge(edge)}
                  title={t("common.edit")}
                >
                  <Icon name="settings" size={13} />
                </button>
                <button
                  type="button"
                  className="icon-button icon-button-danger"
                  onClick={() => deleteEdge.mutate(edge.id)}
                  title={t("common.remove")}
                >
                  <Icon name="trash" size={13} />
                </button>
              </span>
              {edge.label && <span className="rel-reason">{edge.label}</span>}
            </li>
          );
        })}
      </ul>

      {editingEdge && (
        <div className="popover-backdrop" onClick={() => setEditingEdge(null)}>
          <div onClick={(e) => e.stopPropagation()}>
            <EdgeEditPopover
              projectId={projectId}
              edge={editingEdge}
              onDone={() => setEditingEdge(null)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
