import type { EntityField } from "../../api/types";
import { ExternalSheetEmbed } from "../sheet/ExternalSheetEmbed";
import { LSS_EMBED } from "../sheet/externalSheet";

/** Backwards-compatible LSS embed for surfaces that predate templates (the
 * full entity editor). Thin wrapper over the generic ExternalSheetEmbed with
 * the default LongStoryShort embed declaration — all provider logic now lives
 * in sheet/externalSheet.ts, keyed off the `character_sheet_url` text field. */
export function CharacterSheetEmbed({ fields }: { fields: EntityField[] }) {
  return <ExternalSheetEmbed fields={fields} embed={LSS_EMBED} />;
}
