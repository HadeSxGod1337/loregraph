import type { EntityField, ExternalEmbedDef } from "../../api/types";

/** A resolved external character sheet: where to open it, and the URL of its
 * embeddable iframe view. */
export interface ResolvedSheet {
  openUrl: string;
  embedUrl: string;
}

/** A provider turns a share URL into an embeddable sheet, or null if the URL
 * isn't one it recognises. Adding a new service (D&D Beyond, …) is one entry
 * here — no per-service branching anywhere else. */
type Provider = (shareUrl: string) => ResolvedSheet | null;

const LSS_RE = /longstoryshort\.app\/characters\/digital\/([0-9a-f]{24})/;

const lssProvider: Provider = (shareUrl) => {
  const match = shareUrl.match(LSS_RE);
  if (!match) return null;
  return {
    openUrl: shareUrl,
    embedUrl: `https://longstoryshort.app/iframe/characters/digital/${match[1]}/`,
  };
};

const PROVIDERS: Record<string, Provider> = {
  longstoryshort: lssProvider,
};

/** The default LSS embed, for surfaces that predate templates (the full entity
 * editor). Template-driven surfaces pass the template's own external_embed. */
export const LSS_EMBED: ExternalEmbedDef = {
  provider: "longstoryshort",
  url_field: "character_sheet_url",
};

/** Resolve an embed declaration against an entity's fields: reads the share
 * URL from the declared text field, then hands it to the named provider. */
export function resolveExternalSheet(
  embed: ExternalEmbedDef,
  fields: EntityField[],
): ResolvedSheet | null {
  const field = fields.find(
    (f) => f.key === embed.url_field && f.field_type === "text",
  );
  if (!field || typeof field.value !== "string" || field.value === "") {
    return null;
  }
  const provider = PROVIDERS[embed.provider];
  return provider ? provider(field.value) : null;
}
