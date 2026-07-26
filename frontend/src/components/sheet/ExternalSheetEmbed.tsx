import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { EntityField, ExternalEmbedDef } from "../../api/types";
import { Icon } from "../ui/Icon";
import { resolveExternalSheet } from "./externalSheet";

interface ExternalSheetEmbedProps {
  fields: EntityField[];
  embed: ExternalEmbedDef;
}

/** Live external character sheet, collapsed by default — the iframe only
 * mounts on demand so opening an entity never waits on the external service.
 * Generic over providers (see externalSheet.ts): LongStoryShort is one, more
 * plug in without touching this component. */
export function ExternalSheetEmbed({ fields, embed }: ExternalSheetEmbedProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const sheet = resolveExternalSheet(embed, fields);
  if (!sheet) return null;

  return (
    <div className="character-sheet-embed">
      <div className="character-sheet-head">
        <button
          type="button"
          className="button-ghost button-sm"
          onClick={() => setOpen((v) => !v)}
        >
          <Icon
            name="chevron-down"
            size={13}
            className={open ? "rot-180" : undefined}
          />
          {t(open ? "characterSheet.hide" : "characterSheet.show")}
        </button>
        <a
          className="character-sheet-link"
          href={sheet.openUrl}
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
