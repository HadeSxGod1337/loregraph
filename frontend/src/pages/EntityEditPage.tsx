import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useBlocker, useNavigate, useParams } from "react-router-dom";

import type { EntityField } from "../api/types";
import { DEFAULT_ENTITY_TYPES } from "../api/types";
import { AttachmentUploader } from "../components/entity/AttachmentUploader";
import { CharacterSheetEmbed } from "../components/entity/CharacterSheetEmbed";
import { FieldEditor } from "../components/entity/FieldEditor";
import { IconPicker } from "../components/entity/IconPicker";
import { EdgeForm } from "../components/edges/EdgeForm";
import { EdgeList } from "../components/edges/EdgeList";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { useCreateEntity } from "../hooks/useEntities";
import { useDeleteEntity, useEntity, useUpdateEntity } from "../hooks/useEntity";

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
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    if (entity) {
      setType(entity.type);
      setTitle(entity.title);
      setFields(entity.fields);
    }
  }, [entity]);

  // Dirty tracking: compare against the last-loaded server state (or the
  // blank slate for a new entity) so "Save" only lights up with real changes.
  const savedSnapshot = useMemo(
    () =>
      JSON.stringify(
        entity
          ? { type: entity.type, title: entity.title, fields: entity.fields }
          : { type: "npc", title: "", fields: [] },
      ),
    [entity],
  );
  const isDirty = JSON.stringify({ type, title, fields }) !== savedSnapshot;

  // Warn on closing the tab with unsaved edits.
  useEffect(() => {
    if (!isDirty) return;
    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  // In-app navigation guard. Programmatic redirects after create/delete set
  // the skip flag — those flows already resolved the data's fate.
  const skipBlockerRef = useRef(false);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty &&
      !skipBlockerRef.current &&
      currentLocation.pathname !== nextLocation.pathname,
  );

  function handleSave() {
    const data = { type, title, fields };
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

  return (
    <div className="entity-edit-page">
      <nav className="breadcrumb">
        <Link to={`/projects/${projectId}/entities`}>
          ← {t("entityEdit.backToList")}
        </Link>
      </nav>

      <h1>{isNew ? t("entityEdit.newTitle") : t("entityEdit.editTitle")}</h1>

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

      <FieldEditor fields={fields} entityId={id} onChange={setFields} />

      {!isNew && <CharacterSheetEmbed fields={fields} />}

      {!isNew && id && (
        <>
          <EdgeList projectId={projectId!} entityId={id} />
          <EdgeForm projectId={projectId!} entityId={id} />
          <details className="attachments-details">
            <summary>{t("entityEdit.otherFiles")}</summary>
            <AttachmentUploader entityId={id} />
          </details>
        </>
      )}

      <div className="entity-edit-actions">
        <button
          type="button"
          className="button-primary"
          onClick={handleSave}
          disabled={!title || saving || (!isNew && !isDirty)}
        >
          {t("common.save")}
        </button>
        {isDirty && <span className="dirty-hint">{t("entityEdit.unsavedChanges")}</span>}
        <span className="spacer" />
        {!isNew && (
          <button
            type="button"
            className="button-danger"
            onClick={() => setConfirmingDelete(true)}
          >
            {t("common.delete")}
          </button>
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
