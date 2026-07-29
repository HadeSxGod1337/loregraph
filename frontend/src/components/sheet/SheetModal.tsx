import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import type {
  Entity,
  EntityField,
  EntityTemplate,
  FieldType,
  FieldValue,
} from "../../api/types";
import { useUpdateEntity } from "../../hooks/useEntity";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { Icon } from "../ui/Icon";
import { useToast } from "../ui/Toast";
import { applyFieldValue } from "./applyTemplate";
import { ExternalSheetEmbed } from "./ExternalSheetEmbed";
import { SheetRenderer } from "./SheetRenderer";

interface SheetModalProps {
  entity: Entity;
  template: EntityTemplate;
  onClose: () => void;
}

/** Full-width sheet in a fullscreen modal — opened from the graph / drawer.
 * Read-only until "Изменить", which flips the same layout into `fill` mode
 * (editing values, never the layout). Also holds a `print`-mode copy
 * (`.sheet-print-root`) that only the browser's print dialog reveals. */
export function SheetModal({ entity, template, onClose }: SheetModalProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const toast = useToast();
  const updateEntity = useUpdateEntity(entity.project_id, entity.id);

  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState<EntityField[]>(entity.fields);
  const [confirmingClose, setConfirmingClose] = useState(false);

  // Re-sync whenever the server copy changes underneath (another tab, the
  // agent committing a batch) — but never while the DM is mid-edit.
  useEffect(() => {
    if (!editing) setFields(entity.fields);
  }, [entity.fields, editing]);

  const dirty = editing && fields !== entity.fields;

  /** Escape and the backdrop used to discard a half-filled sheet outright:
   * the modal closed, `fields` died with it and nothing had been sent to the
   * server. Ask first whenever there is something to lose. */
  const requestClose = useCallback(() => {
    if (dirty) setConfirmingClose(true);
    else onClose();
  }, [dirty, onClose]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") requestClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [requestClose]);

  function handleFieldChange(key: string, value: FieldValue, fieldType: FieldType) {
    setFields((prev) => applyFieldValue(prev, key, value, fieldType));
  }

  function handleSave() {
    updateEntity.mutate(
      {
        type: entity.type,
        title: entity.title,
        fields,
        template_id: entity.template_id,
      },
      {
        onSuccess: () => {
          toast(t("entityEdit.savedToast"));
          setEditing(false);
        },
      },
    );
  }

  const shown: Entity = editing ? { ...entity, fields } : entity;

  return (
    <div className="sheet-modal-backdrop" onClick={requestClose}>
      <div
        className="sheet-modal"
        role="dialog"
        aria-modal="true"
        aria-label={entity.title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-modal-head">
          <div className="sheet-modal-title">
            <span className="entity-type-badge">{entity.type}</span>
            <h2>{entity.title}</h2>
          </div>
          <div className="sheet-modal-actions">
            {editing ? (
              <>
                <button
                  type="button"
                  className="button-primary button-sm"
                  disabled={updateEntity.isPending}
                  onClick={handleSave}
                >
                  {updateEntity.isPending && (
                    <span className="spinner" aria-hidden="true" />
                  )}
                  {t("common.save")}
                </button>
                <button
                  type="button"
                  className="button-sm button-ghost"
                  onClick={() => {
                    setFields(entity.fields);
                    setEditing(false);
                  }}
                >
                  {t("common.cancel")}
                </button>
              </>
            ) : (
              <button
                type="button"
                className="button-sm"
                onClick={() => setEditing(true)}
              >
                <Icon name="settings" size={14} />
                {t("common.edit")}
              </button>
            )}
            <button
              type="button"
              className="button-sm button-ghost"
              onClick={() =>
                navigate(`/projects/${entity.project_id}/entities/${entity.id}`)
              }
            >
              <Icon name="external-link" size={14} />
              {t("entityDetail.openFullEditor")}
            </button>
            <button type="button" className="button-sm" onClick={() => window.print()}>
              <Icon name="printer" size={14} />
              {t("sheet.print")}
            </button>
            <button
              type="button"
              className="button-sm button-ghost"
              onClick={requestClose}
            >
              <Icon name="x" size={14} />
              {t("common.close")}
            </button>
          </div>
        </div>
        <div className="sheet-modal-body">
          <SheetRenderer
            entity={shown}
            layout={template.layout}
            fieldDefs={template.field_defs}
            mode={editing ? "fill" : "full"}
            onFieldChange={editing ? handleFieldChange : undefined}
          />
          {template.external_embed && (
            <ExternalSheetEmbed
              fields={shown.fields}
              embed={template.external_embed}
            />
          )}
        </div>
      </div>

      {/* Print surface: portalled to <body> so it is a sibling of #root
          rather than a descendant of this modal. @media print then hides
          #root outright and leaves this in normal static flow — an
          absolutely positioned print root cannot paginate, which is why
          printing used to stop after page one. */}
      {createPortal(
        <div className="sheet-print-root">
          <h1 className="sheet-print-title">{entity.title}</h1>
          <SheetRenderer
            entity={shown}
            layout={template.layout}
            fieldDefs={template.field_defs}
            mode="print"
          />
        </div>,
        document.body,
      )}

      {confirmingClose && (
        <ConfirmDialog
          title={t("common.leaveTitle")}
          body={t("common.leaveBody")}
          confirmLabel={t("common.leaveButton")}
          onConfirm={onClose}
          onCancel={() => setConfirmingClose(false)}
        />
      )}
    </div>
  );
}
