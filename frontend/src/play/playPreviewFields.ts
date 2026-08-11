import type { PlayerEntity } from "../api/types";
import type { PreviewField } from "../components/graph/EntityNode";

const MAX_PREVIEW_FIELDS = 3;

/** Preview fields for a player's board node. The player only ever receives
 * whitelisted fields, so this just mirrors the DM's "show on card" choice
 * among the ones they're allowed to see. */
export function getPlayPreviewFields(entity: PlayerEntity): PreviewField[] {
  return entity.fields
    .filter((f) => f.show_on_card)
    .slice(0, MAX_PREVIEW_FIELDS)
    .map((f) => ({
      key: f.key,
      value:
        f.field_type === "tag"
          ? (f.value as string[]).join(", ")
          : String(f.value),
    }));
}
