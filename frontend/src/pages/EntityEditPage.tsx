import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useBlocker, useNavigate, useParams } from "react-router-dom";

import type { EntityField, EntityTemplate, FieldType, FieldValue } from "../api/types";
import { DEFAULT_ENTITY_TYPES } from "../api/types";
import { AttachmentUploader } from "../components/entity/AttachmentUploader";
import { CharacterSheetEmbed } from "../components/entity/CharacterSheetEmbed";
import { EntityPlayerAccessPanel } from "../components/entity/EntityPlayerAccessPanel";
import { FieldEditor } from "../components/entity/FieldEditor";
import { SheetRenderer } from "../components/sheet/SheetRenderer";
import { TemplateSelect } from "../components/sheet/TemplateSelect";
import { applyFieldValue, syncTemplateFields } from "../components/sheet/applyTemplate";
import { IconPicker } from "../components/entity/IconPicker";
import { EdgeForm } from "../components/edges/EdgeForm";
import { EdgeList } from "../components/edges/EdgeList";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { Icon } from "../components/ui/Icon";
import { useToast } from "../components/ui/Toast";
import { translateApiError } from "../i18n/eventText";
import { useCreateEntity } from "../hooks/useEntities";
import { useDeleteEntity, useEntity, useUpdateEntity } from "../hooks/useEntity";
import { useTemplateById } from "../hooks/useTemplates";

// Plain scroll, not a `#fragment` href: the GitHub Pages demo build runs on
// a hash router (see App.tsx), which would otherwise read a same-page
// anchor as a route change and 404.
function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function EntityEditPage() {
  const { t } = useTranslation();
  const { projectId, id } = useParams<{ projectId: string; id: string }>();
  const isNew = id === undefined;
  const navigate = useNavigate();
  const toast = useToast();

  const { data: entity, isLoading } = useEntity(projectId!, id);
  const createEntity = useCreateEntity(projectId!);
  const updateEntity = useUpdateEntity(projectId!, id ?? "");
  const deleteEntity = useDeleteEntity(projectId!);

  const [type, setType] = useState("npc");
  const [title, setTitle] = useState("");
  const [fields, setFields] = useState<EntityField[]>([]);
  const [templateId, setTemplateId] = useState<string | null>(null);
  // Keys the current template selection provisionally added — dropped if the
  // template is deselected before saving (see syncTemplateFields).
  const [templateAddedKeys, setTemplateAddedKeys] = useState<string[]>([]);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  // The player-access panel persists through its own Save button, on its own
  // schedule — this only tracks whether it has edits so the leave-guards
  // below also catch them, without folding them into the main isDirty (which
  // gates the primary Save button and must stay about the fields it saves).
  const [playerAccessDirty, setPlayerAccessDirty] = useState(false);
  const handlePlayerAccessDirty = useCallback((dirty: boolean) => {
    setPlayerAccessDirty(dirty);
  }, []);

  useEffect(() => {
    if (entity) {
      setType(entity.type);
      setTitle(entity.title);
      setFields(entity.fields);
      setTemplateId(entity.template_id);
      setTemplateAddedKeys([]);
    }
  }, [entity]);

  const resolvedTemplate = useTemplateById(projectId!, templateId);

  function handleSelectTemplate(template: EntityTemplate | null) {
    const sync = syncTemplateFields(fields, templateAddedKeys, template);
    setFields(sync.fields);
    setTemplateAddedKeys(sync.addedKeys);
    setTemplateId(template?.id ?? null);
  }

  function handleFieldChange(key: string, value: FieldValue, fieldType: FieldType) {
    setFields((prev) => applyFieldValue(prev, key, value, fieldType));
  }

  // Dirty tracking: compare against the last-loaded server state (or the
  // blank slate for a new entity) so "Save" only lights up with real changes.
  const savedSnapshot = useMemo(
    () =>
      JSON.stringify(
        entity
          ? {
              type: entity.type,
              title: entity.title,
              fields: entity.fields,
              template_id: entity.template_id,
            }
          : { type: "npc", title: "", fields: [], template_id: null },
      ),
    [entity],
  );
  const isDirty =
    JSON.stringify({ type, title, fields, template_id: templateId }) !==
    savedSnapshot;
  const hasUnsavedWork = isDirty || playerAccessDirty;

  // Warn on closing the tab with unsaved edits.
  useEffect(() => {
    if (!hasUnsavedWork) return;
    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [hasUnsavedWork]);

  // In-app navigation guard. Programmatic redirects after create/delete set
  // the skip flag — those flows already resolved the data's fate.
  const skipBlockerRef = useRef(false);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      hasUnsavedWork &&
      !skipBlockerRef.current &&
      currentLocation.pathname !== nextLocation.pathname,
  );

  function handleSave() {
    const data = { type, title, fields, template_id: templateId };
    if (isNew) {
      createEntity.mutate(data, {
        onSuccess: (created) => {
          toast(t("entityEdit.createdToast"));
          skipBlockerRef.current = true;
          navigate(`/projects/${projectId}/entities/${created.id}`);
        },
      });
    } else {
      updateEntity.mutate(data, {
        onSuccess: () => toast(t("entityEdit.savedToast")),
      });
    }
  }

  function handleDeleteConfirmed() {
    if (!id) return;
    deleteEntity.mutate(id, {
      onSuccess: () => {
        toast(t("entityEdit.deletedToast"));
        skipBlockerRef.current = true;
        navigate(`/projects/${projectId}/entities`);
      },
    });
  }

  if (!isNew && isLoading) return <p>{t("common.loading")}</p>;

  const saving = createEntity.isPending || updateEntity.isPending;
  const saveError = createEntity.error ?? updateEntity.error;
  // A new entity is just Basics + Content — short enough that a jump nav
  // would be overhead, not help. It earns its place once the rest of the
  // sections (relationships, attachments, player access, danger zone) exist.
  const showSectionNav = !isNew;

  return (
    <div className="entity-edit-page">
      <nav className="breadcrumb">
        <Link to={`/projects/${projectId}/entities`}>
          ← {t("entityEdit.backToList")}
        </Link>
      </nav>

      <h1>{isNew ? t("entityEdit.newTitle") : t("entityEdit.editTitle")}</h1>

      {showSectionNav && (
        <nav className="entity-edit-toc" aria-label={t("entityEdit.sectionsNavLabel")}>
          <button
            type="button"
            className="type-chip"
            onClick={() => scrollToSection("entity-edit-basics")}
          >
            {t("entityEdit.sectionBasics")}
          </button>
          <button
            type="button"
            className="type-chip"
            onClick={() => scrollToSection("entity-edit-content")}
          >
            {t("entityEdit.sectionContent")}
          </button>
          {id && (
            <button
              type="button"
              className="type-chip"
              onClick={() => scrollToSection("entity-edit-relationships")}
            >
              {t("edges.relationshipsHeading")}
            </button>
          )}
          {id && (
            <button
              type="button"
              className="type-chip"
              onClick={() => scrollToSection("entity-edit-attachments")}
            >
              {t("attachments.heading")}
            </button>
          )}
          {id && entity && (
            <button
              type="button"
              className="type-chip"
              onClick={() => scrollToSection("entity-edit-player-access")}
            >
              {t("playerAccess.title")}
            </button>
          )}
          <button
            type="button"
            className="type-chip"
            onClick={() => scrollToSection("entity-edit-danger")}
          >
            {t("entityEdit.dangerHeading")}
          </button>
        </nav>
      )}

      <section id="entity-edit-basics" className="entity-edit-section">
        <h2 className="entity-edit-section-title">{t("entityEdit.sectionBasics")}</h2>

        <label>
          {t("entityEdit.typeLabel")}
          <input
            list="entity-type-suggestions"
            value={type}
            onChange={(e) => setType(e.target.value)}
          />
          <datalist id="entity-type-suggestions">
            {DEFAULT_ENTITY_TYPES.map((entityType) => (
              <option key={entityType} value={entityType} />
            ))}
          </datalist>
        </label>

        <label>
          {t("entityEdit.titleLabel")}
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>

        <label>{t("entityEdit.iconLabel")}</label>
        <IconPicker projectId={projectId!} entityId={id} icon={entity?.icon ?? null} />
      </section>

      <section id="entity-edit-content" className="entity-edit-section">
        <h2 className="entity-edit-section-title">{t("entityEdit.sectionContent")}</h2>

        <TemplateSelect
          projectId={projectId!}
          value={templateId}
          onSelect={handleSelectTemplate}
        />

        {!isNew && entity && resolvedTemplate ? (
          <div className="entity-sheet-wrap">
            <div className="sheet-toolbar">
              <span className="tpl-chip">
                <Icon name="target" size={13} />
                {t("entityEdit.templateChip", { name: resolvedTemplate.name })}
              </span>
              <span className="field-hint">{t("entityEdit.templateReadOnlyHint")}</span>
              <span className="spacer" />
              <button
                type="button"
                className="button-sm button-ghost"
                onClick={() =>
                  navigate(
                    `/projects/${projectId}/settings?section=templates&template=${resolvedTemplate.id}`,
                  )
                }
              >
                <Icon name="settings" size={13} />
                {t("entityEdit.editTemplate")}
              </button>
            </div>
            <SheetRenderer
              entity={{ ...entity, type, title, fields, template_id: templateId }}
              layout={resolvedTemplate.layout}
              fieldDefs={resolvedTemplate.field_defs}
              mode="fill"
              onFieldChange={handleFieldChange}
            />
          </div>
        ) : (
          <FieldEditor fields={fields} entityId={id} onChange={setFields} />
        )}

        {!isNew && <CharacterSheetEmbed fields={fields} />}
      </section>

      {!isNew && id && (
        <section id="entity-edit-relationships" className="entity-edit-section">
          <EdgeList projectId={projectId!} entityId={id} />
          <EdgeForm projectId={projectId!} entityId={id} />
        </section>
      )}

      {!isNew && id && (
        <section id="entity-edit-attachments" className="entity-edit-section">
          <details className="attachments-details">
            <summary>{t("entityEdit.otherFiles")}</summary>
            <AttachmentUploader entityId={id} />
          </details>
        </section>
      )}

      {!isNew && id && entity && (
        <section id="entity-edit-player-access" className="entity-edit-section">
          <EntityPlayerAccessPanel
            projectId={projectId!}
            entity={entity}
            onDirtyChange={handlePlayerAccessDirty}
          />
        </section>
      )}

      {!isNew && (
        <section id="entity-edit-danger" className="danger-zone settings-card">
          <div className="settings-card-head">
            <h2>{t("entityEdit.dangerHeading")}</h2>
            <p className="field-hint">{t("entityEdit.dangerHint")}</p>
          </div>
          <div className="danger-zone-row">
            <div className="danger-zone-copy">
              <p>{t("common.delete")}</p>
              <p className="field-hint">{t("entityEdit.deleteConfirmBody", { title })}</p>
            </div>
            <button
              type="button"
              className="button-danger"
              onClick={() => setConfirmingDelete(true)}
            >
              {t("common.delete")}
            </button>
          </div>
        </section>
      )}

      <div className="entity-edit-actions">
        <button
          type="button"
          className="button-primary"
          onClick={handleSave}
          disabled={!title || saving || (!isNew && !isDirty)}
        >
          {saving && <span className="spinner" aria-hidden="true" />}
          {saving ? t("entityEdit.saving") : t("common.save")}
        </button>
        <span className={"dirty-hint" + (isDirty ? "" : " settings-saved-hint")}>
          {isDirty ? t("entityEdit.unsavedChanges") : !isNew ? t("entityEdit.allSaved") : ""}
        </span>
        {saveError && (
          <span className="error-text">{translateApiError(saveError, t)}</span>
        )}
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title={t("entityEdit.deleteConfirmTitle")}
          body={t("entityEdit.deleteConfirmBody", { title })}
          confirmLabel={t("common.delete")}
          busy={deleteEntity.isPending}
          onConfirm={handleDeleteConfirmed}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}

      {blocker.state === "blocked" && (
        <ConfirmDialog
          title={t("common.leaveTitle")}
          body={t("common.leaveBody")}
          confirmLabel={t("common.leaveButton")}
          onConfirm={() => blocker.proceed()}
          onCancel={() => blocker.reset()}
        />
      )}
    </div>
  );
}
