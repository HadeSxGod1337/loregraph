import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { API_URL } from "../../api/client";
import type { Edge, EntityField, ProseMirrorDoc } from "../../api/types";
import { useEntities } from "../../hooks/useEntities";
import { useEntity, useDeleteEntity, useUpdateEntity } from "../../hooks/useEntity";
import { useCreateEdge, useDeleteEdge, useEdgesForEntity } from "../../hooks/useEdgesForEntity";
import { EdgeEditPopover } from "../graph/EdgeEditPopover";
import { EdgeList } from "../edges/EdgeList";
import { CharacterSheetEmbed } from "../entity/CharacterSheetEmbed";
import { FieldEditor } from "../entity/FieldEditor";
import { IconPicker } from "../entity/IconPicker";
import { RichTextView } from "../entity/RichTextView";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { Icon } from "../ui/Icon";

const SUGGESTED_EDGE_TYPES = ["contains", "ally_of", "family_of", "enemy_of"];

interface EntityDetailPanelProps {
  projectId: string;
  entityId: string | null;
  /** Currently active/root entity — lets the panel disable "Set as root"
   * when this entity already is it. */
  rootId: string;
  onClose: () => void;
  onNavigate: (entityId: string) => void;
  onDeleted?: (entityId: string) => void;
  /** Makes this entity the graph's root/active entity (Focused mode:
   * re-centers the BFS neighborhood; All mode: just moves the camera). */
  onSetRoot: (entityId: string) => void;
  /** Centers the camera on this entity without changing root — for looking
   * at something while browsing without abandoning the current context. */
  onFocusCamera: (entityId: string) => void;
}

export function EntityDetailPanel({
  projectId,
  entityId,
  rootId,
  onClose,
  onNavigate,
  onDeleted,
  onSetRoot,
  onFocusCamera,
}: EntityDetailPanelProps) {
  const { t } = useTranslation();
  const { data: entity } = useEntity(projectId, entityId ?? undefined);
  const { data: edges } = useEdgesForEntity(projectId, entityId ?? undefined);
  const { data: entities } = useEntities(projectId);
  const updateEntity = useUpdateEntity(projectId, entityId ?? "");
  const deleteEntity = useDeleteEntity(projectId);
  const deleteEdge = useDeleteEdge(projectId);
  const createEdge = useCreateEdge(projectId);

  const [mode, setMode] = useState<"view" | "edit">("view");
  const [title, setTitle] = useState("");
  const [type, setType] = useState("");
  const [fields, setFields] = useState<EntityField[]>([]);
  const [editingEdge, setEditingEdge] = useState<Edge | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [expandedReasons, setExpandedReasons] = useState<Set<string>>(new Set());
  const [addingEdge, setAddingEdge] = useState(false);
  const [newTargetId, setNewTargetId] = useState("");
  const [newEdgeType, setNewEdgeType] = useState("");
  const [newEdgeLabel, setNewEdgeLabel] = useState("");

  useEffect(() => {
    if (entity) {
      setTitle(entity.title);
      setType(entity.type);
      setFields(entity.fields);
    }
  }, [entity]);

  const otherEntities = useMemo(
    () => (entities ?? []).filter((e) => e.id !== entityId),
    [entities, entityId],
  );

  if (!entityId || !entity) return null;

  const titleFor = (id: string) => entities?.find((e) => e.id === id)?.title ?? id;

  function handleSave() {
    updateEntity.mutate({ type, title, fields });
    setMode("view");
  }

  function toggleReason(edgeId: string) {
    setExpandedReasons((prev) => {
      const next = new Set(prev);
      if (next.has(edgeId)) next.delete(edgeId);
      else next.add(edgeId);
      return next;
    });
  }

  function handleAddEdge() {
    if (!newTargetId || !newEdgeType || !entityId) return;
    createEdge.mutate(
      {
        source_entity_id: entityId,
        target_entity_id: newTargetId,
        type: newEdgeType,
        label: newEdgeLabel || null,
      },
      {
        onSuccess: () => {
          setAddingEdge(false);
          setNewTargetId("");
          setNewEdgeType("");
          setNewEdgeLabel("");
        },
      },
    );
  }

  function renderFieldPreview(field: EntityField): string {
    switch (field.field_type) {
      case "tag":
        return (field.value as string[]).join(", ") || t("entityDetail.emptyValue");
      case "attachment":
        return t("entityDetail.attachmentPreview");
      case "rich_text":
        return "";
      default:
        return String(field.value);
    }
  }

  return (
      <div className="panel open">
        <div className="panel-head">
          <button className="panel-close" onClick={onClose}>
            <Icon name="x" size={15} />
          </button>
          <span className="entity-type-badge">{entity.type}</span>
          <h2>{entity.title}</h2>
          <div className="panel-head-nav">
            <button
              type="button"
              className="button-sm"
              onClick={() => onSetRoot(entityId)}
              disabled={entityId === rootId}
              title={t("entityDetail.setAsRoot")}
            >
              <Icon name="target" size={13} />
              {t("entityDetail.setAsRoot")}
            </button>
            <button
              type="button"
              className="button-sm button-ghost"
              onClick={() => onFocusCamera(entityId)}
              title={t("entityDetail.focusCamera")}
            >
              <Icon name="expand" size={13} />
              {t("entityDetail.focusCamera")}
            </button>
          </div>
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

              <CharacterSheetEmbed fields={fields} />

              <div className="panel-section">
                <div className="rel-section-head">
                  <h3>{t("entityDetail.relationships")}</h3>
                  <button
                    type="button"
                    className="icon-button icon-button-accent"
                    onClick={() => setAddingEdge(true)}
                    title={t("entityDetail.addRelationship")}
                  >
                    <Icon name="plus" size={14} />
                  </button>
                </div>

                {addingEdge && (
                  <div className="rel-add-form">
                    <select value={newTargetId} onChange={(e) => setNewTargetId(e.target.value)}>
                      <option value="">{t("entityDetail.selectEntity")}</option>
                      {otherEntities.map((e) => (
                        <option key={e.id} value={e.id}>{e.title}</option>
                      ))}
                    </select>
                    <input
                      list="rel-add-type-suggestions"
                      placeholder={t("edges.edgeTypePlaceholder")}
                      value={newEdgeType}
                      onChange={(e) => setNewEdgeType(e.target.value)}
                    />
                    <datalist id="rel-add-type-suggestions">
                      {SUGGESTED_EDGE_TYPES.map((s) => (
                        <option key={s} value={s} />
                      ))}
                    </datalist>
                    <textarea
                      placeholder={t("edges.reasonPlaceholder")}
                      value={newEdgeLabel}
                      onChange={(e) => setNewEdgeLabel(e.target.value)}
                      rows={2}
                    />
                    <div className="rel-add-actions">
                      <button
                        type="button"
                        className="button-primary button-sm"
                        onClick={handleAddEdge}
                        disabled={!newTargetId || !newEdgeType || createEdge.isPending}
                      >
                        {t("common.create")}
                      </button>
                      <button
                        type="button"
                        className="button-ghost button-sm"
                        onClick={() => {
                          setAddingEdge(false);
                          setNewTargetId("");
                          setNewEdgeType("");
                          setNewEdgeLabel("");
                        }}
                      >
                        {t("common.cancel")}
                      </button>
                    </div>
                  </div>
                )}

                {edges?.length === 0 && !addingEdge && (
                  <p className="field-line">{t("entityDetail.noRelationships")}</p>
                )}
                {edges?.map((edge) => {
                  const isOutgoing = edge.source_entity_id === entityId;
                  const otherId = isOutgoing ? edge.target_entity_id : edge.source_entity_id;
                  const isExpanded = expandedReasons.has(edge.id);
                  return (
                    <div
                      key={edge.id}
                      className="rel-row"
                    >
                      <span className="rel-main">
                        <span className="rel-arrow">{isOutgoing ? "→" : "←"}</span>
                        <span className="rel-type">{edge.type}</span>
                        <span
                          className="rel-title"
                          onClick={() => onNavigate(otherId)}
                          style={{ cursor: "pointer" }}
                        >
                          {titleFor(otherId)}
                        </span>
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
                      {edge.label && (
                        <span
                          className={`rel-reason${isExpanded ? " rel-reason-expanded" : ""}`}
                          onClick={() => toggleReason(edge.id)}
                          title={isExpanded ? undefined : edge.label}
                        >
                          {edge.label}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>

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
            <button
              type="button"
              className="button-primary"
              onClick={handleSave}
              disabled={!title}
            >
              {t("common.save")}
            </button>
          )}
          <Link
            to={`/projects/${projectId}/entities/${entityId}`}
            className="link-button"
          >
            {t("entityDetail.openFullEditor")}
          </Link>
          <span className="spacer" />
          <button
            type="button"
            className="icon-button icon-button-danger"
            onClick={() => setConfirmingDelete(true)}
            title={t("common.delete")}
          >
            <Icon name="trash" size={15} />
          </button>
        </div>

        {confirmingDelete && (
          <ConfirmDialog
            title={t("entityDetail.deleteConfirmTitle")}
            body={t("entityDetail.deleteConfirmBody", { title: entity.title })}
            confirmLabel={t("common.delete")}
            busy={deleteEntity.isPending}
            onConfirm={() => {
              deleteEntity.mutate(entityId, {
                onSuccess: () => {
                  onDeleted?.(entityId);
                  onClose();
                },
              });
            }}
            onCancel={() => setConfirmingDelete(false)}
          />
        )}
      </div>
  );
}
