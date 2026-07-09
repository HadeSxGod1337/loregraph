import type { Entity } from "../../api/types";
import type { PreviewField } from "./EntityNode";

const MAX_PREVIEW_FIELDS = 3;

/** Fields the user explicitly marked "show on card" (via the field editor's
 * per-field toggle), shown directly on the graph card — e.g. a "level" or
 * "role" field on an NPC — capped so the card doesn't grow unbounded. */
export function getPreviewFields(entity: Entity): PreviewField[] {
  return entity.fields
    .filter((f) => f.show_on_card)
    .slice(0, MAX_PREVIEW_FIELDS)
    .map((f) => ({
      key: f.key,
      value: f.field_type === "tag" ? (f.value as string[]).join(", ") : String(f.value),
    }));
}
