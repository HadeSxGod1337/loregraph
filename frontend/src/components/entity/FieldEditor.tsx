import type { EntityField, FieldType, FieldValue } from "../../api/types";
import { FieldRow } from "./FieldRow";
import { FieldTypePicker } from "./FieldTypePicker";

const DEFAULT_VALUES: Record<FieldType, FieldValue> = {
  text: "",
  rich_text: { type: "doc", content: [{ type: "paragraph" }] },
  number: 0,
  tag: [],
  attachment: { attachment_id: "", url: "" },
};

interface FieldEditorProps {
  fields: EntityField[];
  entityId: string | undefined;
  onChange: (fields: EntityField[]) => void;
}

export function FieldEditor({ fields, entityId, onChange }: FieldEditorProps) {
  function addField(fieldType: FieldType) {
    onChange([
      ...fields,
      { key: "", field_type: fieldType, value: DEFAULT_VALUES[fieldType], show_on_card: false },
    ]);
  }

  function updateField(index: number, next: EntityField) {
    onChange(fields.map((f, i) => (i === index ? next : f)));
  }

  function removeField(index: number) {
    onChange(fields.filter((_, i) => i !== index));
  }

  return (
    <div className="field-editor">
      {fields.map((field, i) => (
        <FieldRow
          key={i}
          field={field}
          entityId={entityId}
          onChange={(next) => updateField(i, next)}
          onRemove={() => removeField(i)}
        />
      ))}
      <FieldTypePicker onAdd={addField} />
    </div>
  );
}
