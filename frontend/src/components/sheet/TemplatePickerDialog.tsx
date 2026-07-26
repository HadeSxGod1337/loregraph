import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Icon } from "../ui/Icon";
import { useInstantiateTemplate, useTemplates } from "../../hooks/useTemplates";

interface TemplatePickerDialogProps {
  projectId: string;
  onClose: () => void;
  onCreated: (entityId: string) => void;
}

/** "New from template" — pick a template, name the entity, and it is created
 * pre-filled through the instantiate endpoint. */
export function TemplatePickerDialog({
  projectId,
  onClose,
  onCreated,
}: TemplatePickerDialogProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: templates } = useTemplates(projectId);
  const instantiate = useInstantiateTemplate(projectId);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState("");

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const selected = templates?.find((tpl) => tpl.id === selectedId) ?? null;

  function handleCreate() {
    if (!selected) return;
    const finalTitle = title.trim() || selected.name;
    instantiate.mutate(
      { templateId: selected.id, title: finalTitle },
      { onSuccess: (entity) => onCreated(entity.id) },
    );
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t("sheet.newFromTemplate")}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{t("sheet.newFromTemplate")}</h2>

        <button
          type="button"
          className="button-sm"
          onClick={() => navigate(`/projects/${projectId}/settings?section=templates`)}
        >
          <Icon name="layers" size={13} />
          {t("templates.manage")}
        </button>

        <div className="template-picker-list">
          {(templates ?? []).map((tpl) => (
            <button
              key={tpl.id}
              type="button"
              className={
                tpl.id === selectedId
                  ? "template-picker-item active"
                  : "template-picker-item"
              }
              onClick={() => setSelectedId(tpl.id)}
            >
              <span className="template-picker-name">{tpl.name}</span>
              <span className="entity-type-badge">{tpl.entity_type}</span>
              {tpl.is_builtin && (
                <span className="template-picker-builtin">
                  {t("sheet.builtin")}
                </span>
              )}
            </button>
          ))}
        </div>

        {selected && (
          <input
            autoFocus
            placeholder={selected.name}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
            }}
          />
        )}

        <div className="dialog-actions">
          <button type="button" className="button-ghost" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className="button-primary"
            disabled={!selected || instantiate.isPending}
            onClick={handleCreate}
          >
            <Icon name="plus" size={14} />
            {t("common.create")}
          </button>
        </div>
      </div>
    </div>
  );
}
