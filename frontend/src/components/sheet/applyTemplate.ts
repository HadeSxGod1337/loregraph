import type {
  EntityField,
  EntityTemplate,
  FieldType,
  FieldValue,
} from "../../api/types";

export function emptyValue(fieldType: FieldType): FieldValue {
  switch (fieldType) {
    case "rich_text":
      return { type: "doc", content: [{ type: "paragraph" }] };
    case "number":
      return 0;
    case "tag":
      return [];
    case "attachment":
      return { attachment_id: "", url: "" };
    default:
      return "";
  }
}

export interface TemplateSync {
  fields: EntityField[];
  addedKeys: string[];
}

/** Reconcile an entity's editable fields with a newly chosen template.
 *
 * Fields the previous selection provisionally added (`prevAddedKeys`) are
 * dropped first, so deselecting a template before saving reverts to the
 * original fields. Then the new template's missing fields are appended empty.
 * `template === null` just removes the provisional fields. */
export function syncTemplateFields(
  current: EntityField[],
  prevAddedKeys: string[],
  template: EntityTemplate | null,
): TemplateSync {
  const base = current.filter((f) => !prevAddedKeys.includes(f.key));
  if (!template) return { fields: base, addedKeys: [] };

  const existing = new Set(base.map((f) => f.key));
  const toAdd = template.field_defs.filter(
    (def) => def.key !== "" && !existing.has(def.key),
  );
  const added: EntityField[] = toAdd.map((def) => ({
    key: def.key,
    field_type: def.field_type,
    value: def.default_value ?? emptyValue(def.field_type),
    show_on_card: def.show_on_card,
  }));
  return {
    fields: [...base, ...added],
    addedKeys: toAdd.map((def) => def.key),
  };
}
