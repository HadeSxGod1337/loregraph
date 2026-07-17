import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { EntityField } from "../../api/types";
import { Icon } from "../ui/Icon";

/* Convention shared with the backend LSS connector (parser.py): an entity
 * imported from LongStoryShort carries its share link in a plain text field
 * `character_sheet_url` — that field, not a dedicated field type, drives
 * this embed. LSS ships an official iframe route (built for their Owlbear
 * integration), so the sheet renders live without any API access. */
const LSS_SHEET_RE = /longstoryshort\.app\/characters\/digital\/([0-9a-f]{24})/;
const SHEET_URL_KEY = "character_sheet_url";

interface SheetRef {
  url: string;
  embedUrl: string;
}

export function findCharacterSheet(fields: EntityField[]): SheetRef | null {
  const field = fields.find(
    (f) => f.key === SHEET_URL_KEY && f.field_type === "text",
  );
  if (!field || typeof field.value !== "string") return null;
  const match = field.value.match(LSS_SHEET_RE);
  if (!match) return null;
  return {
    url: field.value,
    embedUrl: `https://longstoryshort.app/iframe/characters/digital/${match[1]}/`,
  };
}

/** Live character sheet, collapsed by default — the iframe only mounts on
 * demand so opening an entity never waits on longstoryshort.app. */
export function CharacterSheetEmbed({ fields }: { fields: EntityField[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const sheet = findCharacterSheet(fields);
  if (!sheet) return null;

  return (
    <div className="character-sheet-embed">
      <div className="character-sheet-head">
        <button
          type="button"
          className="button-ghost button-sm"
          onClick={() => setOpen((v) => !v)}
        >
          <Icon name="chevron-down" size={13} className={open ? "rot-180" : undefined} />
          {t(open ? "characterSheet.hide" : "characterSheet.show")}
        </button>
        <a
          className="character-sheet-link"
          href={sheet.url}
          target="_blank"
          rel="noreferrer noopener"
        >
          <Icon name="external-link" size={13} />
          {t("characterSheet.openInLss")}
        </a>
      </div>
      {open && (
        <iframe
          className="character-sheet-iframe"
          src={sheet.embedUrl}
          title={t("characterSheet.title")}
          loading="lazy"
        />
      )}
    </div>
  );
}
