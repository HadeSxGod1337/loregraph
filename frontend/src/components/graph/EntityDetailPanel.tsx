import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { API_URL } from "../../api/client";
import type { EntityField, ProseMirrorDoc } from "../../api/types";
import { useEntities } from "../../hooks/useEntities";
import { useEntity, useUpdateEntity } from "../../hooks/useEntity";
import { useEdgesForEntity } from "../../hooks/useEdgesForEntity";
import { EdgeList } from "../edges/EdgeList";
import { FieldEditor } from "../entity/FieldEditor";
import { IconPicker } from "../entity/IconPicker";
import { RichTextView } from "../entity/RichTextView";

interface EntityDetailPanelProps {
  projectId: string;
  entityId: string | null;
  onClose: () => void;
  onNavigate: (entityId: string) => void;
}

export function EntityDetailPanel({
  projectId,
  entityId,
  onClose,
  onNavigate,
}: EntityDetailPanelProps) {
  const { t } = useTranslation();
  const { data: entity } = useEntity(projectId, entityId ?? undefined);
  const { data: edges } = useEdgesForEntity(projectId, entityId ?? undefined);
  const { data: entities } = useEntities(projectId);
  const updateEntity = useUpdateEntity(projectId, entityId ?? "");

  const [mode, setMode] = useState<"view" | "edit">("view");
  const [title, setTitle] = useState("");
  const [type, setType] = useState("");
  const [fields, setFields] = useState<EntityField[]>([]);

  // `key={selectedEntityId}` on this component (see GraphViewPage) forces a
  // full remount per entity — otherwise React reuses this component's
  // subtree across different entities whenever the fields array happens to
  // line up (same length/types), and Tiptap instances inside don't
  // reinitialize on their own, leaking one entity's rich text into another's
  // panel. Remounting also means `mode` naturally resets to "view" per
  // entity without a separate effect.
  useEffect(() => {
    if (entity) {
      setTitle(entity.title);
      setType(entity.type);
      setFields(entity.fields);
    }
  }, [entity]);

  if (!entityId || !entity) return null;

  const titleFor = (id: string) => entities?.find((e) => e.id === id)?.title ?? id;

  function handleSave() {
    updateEntity.mutate({ type, title, fields });
    setMode("view");
  }

  function renderFieldPreview(field: EntityField): string {
    switch (field.field_type) {
      case "tag":
        return (field.value as string[]).join(", ") || t("entityDetail.emptyValue");
      case "attachment":
        return t("entityDetail.attachmentPreview");
      case "rich_text":
        return ""; // rendered via RichTextView instead, see the field-line branch above
      default:
        return String(field.value);
    }
  }

  return (
      <div className="panel open">
        <div className="panel-head">
          <button className="panel-close" onClick={onClose}>
            ✕
          </button>
          <span className="entity-type-badge">{entity.type}</span>
          <h2>{entity.title}</h2>
        </div>

        <div className="panel-body">
          {entity.icon && (
            <div className="panel-section">
              <img className="portrait" src={API_URL + entity.icon.url} alt="" />
            </div>
          )}

          {mode === "view" ? (
            <>
              <div className="panel-section">
                <h3>{t("entityDetail.fields")}</h3>
                {fields.length === 0 && (
                  <p className="field-line">{t("entityDetail.noFields")}</p>
                )}
                {fields.map((f) => (
                  <div className="field-line" key={f.key}>
                    <span className="k">{f.key}</span>
                    {f.field_type === "rich_text" ? (
                      <div className="v v-rich-text">
                        <RichTextView value={f.value as ProseMirrorDoc} />
                      </div>
                    ) : (
                      <span className="v">{renderFieldPreview(f)}</span>
                    )}
                  </div>
                ))}
              </div>

              <div className="panel-section">
                <h3>{t("entityDetail.relationships")}</h3>
                {edges?.length === 0 && (
                  <p className="field-line">{t("entityDetail.noRelationships")}</p>
                )}
                {edges?.map((edge) => {
                  const isOutgoing = edge.source_entity_id === entityId;
                  const otherId = isOutgoing ? edge.target_entity_id : edge.source_entity_id;
                  return (
                    <div
                      key={edge.id}
                      className="rel-row"
                      onClick={() => onNavigate(otherId)}
                    >
                      <span className="rel-arrow">{isOutgoing ? "→" : "←"}</span>
                      <span className="rel-type">{edge.type}</span>
                      <span className="rel-title">{titleFor(otherId)}</span>
                      {edge.label && <span className="rel-reason">{edge.label}</span>}
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <>
              <div className="panel-section">
                <h3>{t("entityDetail.icon")}</h3>
                <IconPicker projectId={projectId} entityId={entityId} icon={entity.icon} />
              </div>
              <div className="panel-section">
                <h3>{t("entityDetail.titleAndType")}</h3>
                <input value={title} onChange={(e) => setTitle(e.target.value)} />
                <input value={type} onChange={(e) => setType(e.target.value)} />
              </div>
              <div className="panel-section">
                <h3>{t("entityDetail.fields")}</h3>
                <FieldEditor fields={fields} entityId={entityId} onChange={setFields} />
              </div>
              <div className="panel-section">
                <EdgeList projectId={projectId} entityId={entityId} />
              </div>
            </>
          )}
        </div>

        <div className="panel-actions">
          {mode === "view" ? (
            <button type="button" onClick={() => setMode("edit")}>
              {t("common.edit")}
            </button>
          ) : (
            <button type="button" onClick={handleSave} disabled={!title}>
              {t("common.save")}
            </button>
          )}
          <Link to={`/projects/${projectId}/entities/${entityId}`}>
            {t("entityDetail.openFullEditor")}
          </Link>
        </div>
      </div>
  );
}
