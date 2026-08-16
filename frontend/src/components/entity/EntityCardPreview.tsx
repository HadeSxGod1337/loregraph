import { useTranslation } from "react-i18next";

import type { EntityField } from "../../api/types";
import { useObjectUrl } from "../../hooks/useObjectUrl";
import { entityCardSubtitle } from "../../lib/entityCard";
import { typeColor, typeSoftBackground } from "../../lib/typeColor";

interface EntityCardPreviewProps {
  type: string;
  title: string;
  fields: EntityField[];
  iconFile: File | null;
}

/** How this entity's card will look in the list and on the graph once
 * created — same row markup as EntityTreeRow, just inert. Pure local state,
 * so it costs nothing to keep live while the create form is filled in. */
export function EntityCardPreview({ type, title, fields, iconFile }: EntityCardPreviewProps) {
  const { t } = useTranslation();
  const iconUrl = useObjectUrl(iconFile);
  const subtitle = entityCardSubtitle(fields, t);
  const displayTitle = title.trim() || t("entityEdit.previewUntitled");

  return (
    <div className="entity-card-preview">
      <span className="entity-card-preview-eyebrow">{t("entityEdit.previewLabel")}</span>
      <div className="entity-list-item entity-card-preview-row">
        {iconUrl ? (
          <img className="entity-avatar" src={iconUrl} alt="" />
        ) : (
          <span
            className="entity-avatar"
            style={{ background: typeSoftBackground(type), color: typeColor(type) }}
          >
            {displayTitle.trim().charAt(0).toUpperCase()}
          </span>
        )}
        <span className="entity-list-main">
          <span className="entity-list-title">{displayTitle}</span>
          {subtitle && <span className="entity-list-sub">{subtitle}</span>}
        </span>
        <span
          className="entity-type-badge"
          style={{
            background: typeSoftBackground(type),
            color: typeColor(type),
            borderColor: "transparent",
          }}
        >
          {type}
        </span>
      </div>
    </div>
  );
}
