import type {
  EntityField,
  EntityTemplate,
  FieldType,
  FieldValue,
} from "../../api/types";

/** Mirrors EMPTY_FIELD_DEFAULTS in schemas/entity_template.py — the backend
 * rejects a value whose shape does not match its field type, so every type
 * needs its own empty here. Exhaustive on purpose: a `default:` branch is what
 * let `boolean` silently fall through to `""` and 422 the whole save. */
export function emptyValue(fieldType: FieldType): FieldValue {
  switch (fieldType) {
    case "text":
      return "";
    case "rich_text":
      return { type: "doc", content: [{ type: "paragraph" }] };
    case "number":
      return 0;
    case "boolean":
      return false;
    case "tag":
      return [];
    case "attachment":
      return { attachment_id: "", url: "" };
  }
}

/** Write a value into an entity's field list, appending the field when it is
 * not there yet.
 *
 * The append is the point: a sheet renders every block its template declares,
 * including ones whose field the entity has never carried (the template gained
 * a field after this entity was made, or instantiation skipped an attachment
 * with no default). Without this those slots stayed permanently read-only —
 * the DM could see "Пассивная внимательность" on the sheet and had no way to
 * fill it in, because the plain field editor is hidden while a template is
 * bound. */
export function applyFieldValue(
  fields: EntityField[],
  key: string,
  value: FieldValue,
  fieldType: FieldType,
): EntityField[] {
  if (fields.some((f) => f.key === key)) {
    return fields.map((f) => (f.key === key ? { ...f, value } : f));
  }
  return [...fields, { key, field_type: fieldType, value, show_on_card: false }];
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
