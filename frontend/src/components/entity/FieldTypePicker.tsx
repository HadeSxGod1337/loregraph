import { useTranslation } from "react-i18next";

import type { FieldType } from "../../api/types";
import { HelpIcon } from "../ui/Tooltip";

const ADDABLE_TYPES: { value: FieldType; labelKey: string }[] = [
  { value: "text", labelKey: "fields.typeText" },
  { value: "rich_text", labelKey: "fields.typeRichText" },
  { value: "number", labelKey: "fields.typeNumber" },
  { value: "tag", labelKey: "fields.typeTags" },
];

export function FieldTypePicker({ onAdd }: { onAdd: (fieldType: FieldType) => void }) {
  const { t } = useTranslation();
  return (
    <div className="field-type-picker">
      <HelpIcon content={t("tooltips.fieldType")} side="top" />
      {ADDABLE_TYPES.map((entry) => (
        <button
          key={entry.value}
          type="button"
          className="field-type-picker-button"
          onClick={() => onAdd(entry.value)}
        >
          + {t(entry.labelKey)}
        </button>
      ))}
    </div>
  );
}
