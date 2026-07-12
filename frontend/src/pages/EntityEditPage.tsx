import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import type { EntityField } from "../api/types";
import { DEFAULT_ENTITY_TYPES } from "../api/types";
import { AttachmentUploader } from "../components/entity/AttachmentUploader";
import { FieldEditor } from "../components/entity/FieldEditor";
import { IconPicker } from "../components/entity/IconPicker";
import { EdgeForm } from "../components/edges/EdgeForm";
import { EdgeList } from "../components/edges/EdgeList";
import { useCreateEntity } from "../hooks/useEntities";
import { useDeleteEntity, useEntity, useUpdateEntity } from "../hooks/useEntity";

export function EntityEditPage() {
  const { t } = useTranslation();
  const { projectId, id } = useParams<{ projectId: string; id: string }>();
  const isNew = id === undefined;
  const navigate = useNavigate();

  const { data: entity, isLoading } = useEntity(projectId!, id);
  const createEntity = useCreateEntity(projectId!);
  const updateEntity = useUpdateEntity(projectId!, id ?? "");
  const deleteEntity = useDeleteEntity(projectId!);

  const [type, setType] = useState("npc");
  const [title, setTitle] = useState("");
  const [fields, setFields] = useState<EntityField[]>([]);

  useEffect(() => {
    if (entity) {
      setType(entity.type);
      setTitle(entity.title);
      setFields(entity.fields);
    }
  }, [entity]);

  function handleSave() {
    const data = { type, title, fields };
    if (isNew) {
      createEntity.mutate(data, {
        onSuccess: (created) => navigate(`/projects/${projectId}/entities/${created.id}`),
      });
    } else {
      updateEntity.mutate(data);
    }
  }

  function handleDelete() {
    if (!id) return;
    deleteEntity.mutate(id, { onSuccess: () => navigate(`/projects/${projectId}/entities`) });
  }

  if (!isNew && isLoading) return <p>{t("common.loading")}</p>;

  return (
    <div className="entity-edit-page">
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

      <div className="entity-edit-actions">
        <button type="button" onClick={handleSave} disabled={!title}>
          {t("common.save")}
        </button>
        {!isNew && (
          <button type="button" className="button-danger" onClick={handleDelete}>
            {t("common.delete")}
          </button>
        )}
      </div>

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
    </div>
  );
}
