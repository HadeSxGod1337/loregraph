import { useEffect, useState } from "react";
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
  const { id } = useParams<{ id: string }>();
  const isNew = id === undefined;
  const navigate = useNavigate();

  const { data: entity, isLoading } = useEntity(id);
  const createEntity = useCreateEntity();
  const updateEntity = useUpdateEntity(id ?? "");
  const deleteEntity = useDeleteEntity();

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
        onSuccess: (created) => navigate(`/entities/${created.id}`),
      });
    } else {
      updateEntity.mutate(data);
    }
  }

  function handleDelete() {
    if (!id) return;
    deleteEntity.mutate(id, { onSuccess: () => navigate("/") });
  }

  if (!isNew && isLoading) return <p>Loading...</p>;

  return (
    <div className="entity-edit-page">
      <h1>{isNew ? "New Entity" : "Edit Entity"}</h1>

      <label>
        Type
        <input
          list="entity-type-suggestions"
          value={type}
          onChange={(e) => setType(e.target.value)}
        />
        <datalist id="entity-type-suggestions">
          {DEFAULT_ENTITY_TYPES.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </label>

      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>

      <label>Icon</label>
      <IconPicker entityId={id} icon={entity?.icon ?? null} />

      <FieldEditor fields={fields} entityId={id} onChange={setFields} />

      <div className="entity-edit-actions">
        <button type="button" onClick={handleSave} disabled={!title}>
          Save
        </button>
        {!isNew && (
          <button type="button" className="button-danger" onClick={handleDelete}>
            Delete
          </button>
        )}
      </div>

      {!isNew && id && (
        <>
          <EdgeList entityId={id} />
          <EdgeForm entityId={id} />
          <details className="attachments-details">
            <summary>Other files</summary>
            <AttachmentUploader entityId={id} />
          </details>
        </>
      )}
    </div>
  );
}
