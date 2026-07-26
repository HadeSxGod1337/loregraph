import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { templatesApi } from "../../../api/templates";
import type { EntityTemplate, EntityTemplateCreate } from "../../../api/types";
import { useDeleteTemplate, useTemplates } from "../../../hooks/useTemplates";
import { translateApiError } from "../../../i18n/eventText";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { Icon } from "../../ui/Icon";
import { useToast } from "../../ui/Toast";
import { TemplateDesigner } from "./TemplateDesigner";
import { emptyDraft, toDraft } from "./draft";

interface EditingState {
  /** Persisted template id when editing an existing user template; undefined
   * for a brand-new or duplicated template (both create on save). */
  id?: string;
  draft: EntityTemplateCreate;
}

export function TemplatesPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data: templates } = useTemplates(projectId);
  const deleteTemplate = useDeleteTemplate(projectId);

  const [editing, setEditing] = useState<EditingState | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

  // "Изменить шаблон" from the entity editor links here with ?template=<id>
  // — open its designer directly instead of leaving the DM to find it in
  // the list. Builtins open as a duplicate (they're read-only).
  useEffect(() => {
    const wanted = searchParams.get("template");
    if (!wanted || editing || !templates) return;
    const template = templates.find((tpl) => tpl.id === wanted);
    if (!template) return;
    if (template.is_builtin) duplicate(template);
    else setEditing({ id: template.id, draft: toDraft(template) });
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("template");
        return next;
      },
      { replace: true },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, templates, editing]);

  const save = useMutation({
    mutationFn: ({ id, draft }: EditingState) =>
      id
        ? templatesApi.update(projectId, id, draft)
        : templatesApi.create(projectId, draft),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["templates", projectId] });
      toast(t("templates.saved"));
      setEditing(null);
    },
  });

  const deletingTemplate = templates?.find((tpl) => tpl.id === deletingId) ?? null;

  function duplicate(template: EntityTemplate) {
    setEditing({
      draft: { ...toDraft(template), name: `${template.name} (${t("templates.copy")})` },
    });
  }

  return (
    <section className="settings-card">
      <div className="settings-card-head">
        <h2>{t("templates.title")}</h2>
        <p className="field-hint">{t("templates.hint")}</p>
      </div>

      <div className="templates-list">
        {(templates ?? []).map((template) => (
          <div className="templates-row" key={template.id}>
            <span className="templates-row-name">{template.name}</span>
            <span className="entity-type-badge">{template.entity_type}</span>
            {template.is_builtin && (
              <span className="templates-builtin">{t("sheet.builtin")}</span>
            )}
            <span className="spacer" />
            {template.is_builtin ? (
              <button
                type="button"
                className="button-sm button-ghost"
                onClick={() => duplicate(template)}
              >
                <Icon name="layers" size={13} />
                {t("templates.duplicate")}
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="button-sm button-ghost"
                  onClick={() => setEditing({ id: template.id, draft: toDraft(template) })}
                >
                  <Icon name="settings" size={13} />
                  {t("common.edit")}
                </button>
                <button
                  type="button"
                  className="icon-button icon-button-danger"
                  onClick={() => setDeletingId(template.id)}
                  title={t("common.delete")}
                >
                  <Icon name="trash" size={13} />
                </button>
              </>
            )}
          </div>
        ))}
      </div>

      <button
        type="button"
        className="button-primary"
        onClick={() => setEditing({ draft: emptyDraft() })}
      >
        <Icon name="plus" size={14} />
        {t("templates.newTemplate")}
      </button>

      {save.isError && (
        <p className="error-text">{translateApiError(save.error, t)}</p>
      )}

      {editing && (
        <TemplateDesigner
          projectId={projectId}
          initial={editing.draft}
          saving={save.isPending}
          onSave={(draft) => save.mutate({ id: editing.id, draft })}
          onClose={() => setEditing(null)}
        />
      )}

      {deletingTemplate && (
        <ConfirmDialog
          title={t("templates.deleteConfirmTitle")}
          body={t("templates.deleteConfirmBody", { name: deletingTemplate.name })}
          confirmLabel={t("common.delete")}
          busy={deleteTemplate.isPending}
          onConfirm={() =>
            deleteTemplate.mutate(deletingTemplate.id, {
              onSuccess: () => {
                toast(t("templates.deleted"));
                setDeletingId(null);
              },
            })
          }
          onCancel={() => setDeletingId(null)}
        />
      )}
    </section>
  );
}
