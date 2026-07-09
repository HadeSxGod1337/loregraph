import type { FieldType } from "../../api/types";

const ADDABLE_TYPES: { value: FieldType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "rich_text", label: "Rich text" },
  { value: "number", label: "Number" },
  { value: "tag", label: "Tags" },
];

export function FieldTypePicker({ onAdd }: { onAdd: (fieldType: FieldType) => void }) {
  return (
    <div className="field-type-picker">
      {ADDABLE_TYPES.map((t) => (
        <button
          key={t.value}
          type="button"
          className="field-type-picker-button"
          onClick={() => onAdd(t.value)}
        >
          + {t.label}
        </button>
      ))}
    </div>
  );
}
