import type { EntityField } from "../api/types";

/** Second line of an entity's card: the first short text field marked to
 * show there (the entity's own "tagline"), else the first text field, else
 * a field count. Shared by the entity list row and the create-flow card
 * preview so both agree on what a card's subtitle will say. */
export function entityCardSubtitle(
  fields: EntityField[],
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const preview = fields.find(
    (field) =>
      field.show_on_card &&
      field.field_type === "text" &&
      typeof field.value === "string" &&
      field.value.trim() !== "",
  );
  if (preview) return preview.value as string;
  const firstText = fields.find(
    (field) =>
      field.field_type === "text" &&
      typeof field.value === "string" &&
      field.value.trim() !== "",
  );
  if (firstText) return firstText.value as string;
  if (fields.length > 0) {
    return t("entities.fieldCount", { count: fields.length });
  }
  return "";
}
