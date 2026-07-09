import type { EntityField, ProseMirrorDoc } from "../../api/types";
import { RichTextField } from "./RichTextField";

// rich_text/attachment values aren't useful as a compact card preview, so
// the toggle to show a field on the graph card only applies to these.
const CARD_ELIGIBLE_TYPES = new Set(["text", "number", "tag"]);

interface FieldRowProps {
  field: EntityField;
  entityId: string | undefined;
  onChange: (field: EntityField) => void;
  onRemove: () => void;
}

export function FieldRow({ field, entityId, onChange, onRemove }: FieldRowProps) {
  return (
    <div className="field-row">
      <input
        className="field-row-key"
        value={field.key}
        placeholder="field name"
        onChange={(e) => onChange({ ...field, key: e.target.value })}
      />
      <div className="field-row-value">
        {renderValueInput(field, entityId, onChange)}
      </div>
      <div className="field-row-actions">
        {CARD_ELIGIBLE_TYPES.has(field.field_type) && (
          <label className="field-row-card-toggle" title="Show this field on the graph card">
            <input
              type="checkbox"
              checked={field.show_on_card}
              onChange={(e) => onChange({ ...field, show_on_card: e.target.checked })}
            />
            on card
          </label>
        )}
        <button
          type="button"
          className="field-row-remove button-danger"
          onClick={onRemove}
          title="Remove this field"
        >
          Remove
        </button>
      </div>
    </div>
  );
}

function renderValueInput(
  field: EntityField,
  entityId: string | undefined,
  onChange: (field: EntityField) => void,
) {
  switch (field.field_type) {
    case "text":
      return (
        <input
          value={field.value as string}
          onChange={(e) => onChange({ ...field, value: e.target.value })}
        />
      );
    case "rich_text":
      return (
        <RichTextField
          value={field.value as ProseMirrorDoc}
          entityId={entityId}
          onChange={(doc) => onChange({ ...field, value: doc })}
        />
      );
    case "number":
      return (
        <input
          type="number"
          value={field.value as number}
          onChange={(e) => onChange({ ...field, value: Number(e.target.value) })}
        />
      );
    case "tag":
      return (
        <input
          placeholder="comma, separated, tags"
          value={(field.value as string[]).join(", ")}
          onChange={(e) =>
            onChange({
              ...field,
              value: e.target.value
                .split(",")
                .map((v) => v.trim())
                .filter((v) => v.length > 0),
            })
          }
        />
      );
    case "attachment":
      return <span className="field-row-attachment">(attachment reference)</span>;
  }
}
