import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import type { DraftEntity, DraftRelationship } from "../../api/agent";
import { typeColor, typeSoftBackground } from "../../lib/typeColor";
import { Icon } from "../ui/Icon";

interface DraftPreviewDrawerProps {
  entity: DraftEntity;
  relationships: DraftRelationship[];
  /** Resolves a draft ref or existing entity id to a display title. */
  targetName: (ref: string) => string;
  onClose: () => void;
}

/** Read-only side drawer with the full contents of one draft entity. The
 * dashed edge and the banner make it unmistakably a preview: nothing here is
 * canon until the batch is approved. */
export function DraftPreviewDrawer({
  entity,
  relationships,
  targetName,
  onClose,
}: DraftPreviewDrawerProps) {
  const { t } = useTranslation();
  const color = typeColor(entity.type);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const related = relationships.filter(
    (relationship) =>
      relationship.source_ref === entity.ref || relationship.target_ref === entity.ref,
  );

  return (
    <div className="draft-preview-backdrop" onClick={onClose}>
      <aside
        className="draft-preview-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={entity.title}
        onClick={(e) => e.stopPropagation()}
      >
        <p className="draft-preview-banner">
          <Icon name="sparkles" size={13} /> {t("assistant.review.previewBanner")}
        </p>

        <div className="draft-preview-head">
          <button
            type="button"
            className="panel-close"
            aria-label={t("common.cancel")}
            onClick={onClose}
          >
            <Icon name="x" size={15} />
          </button>
          <div className="draft-preview-badges">
            <span className="draft-preview-badge">
              {t("assistant.review.previewBadge")}
            </span>
            <span
              className="entity-type-badge"
              style={{
                background: typeSoftBackground(entity.type),
                color,
                borderColor: "transparent",
              }}
            >
              {entity.type}
            </span>
          </div>
          <h2>{entity.title}</h2>
        </div>

        <div className="draft-preview-body">
          {entity.summary && (
            <div className="panel-section">
              <h3>{t("assistant.review.summaryHeading")}</h3>
              <p className="draft-preview-summary">{entity.summary}</p>
            </div>
          )}

          {entity.fields.length > 0 && (
            <div className="panel-section">
              <h3>{t("entityDetail.fields")}</h3>
              {entity.fields.map((field) => (
                <div className="field-line" key={field.key}>
                  <span className="k">{field.key}</span>
                  <span className="v">{field.value}</span>
                </div>
              ))}
            </div>
          )}

          {related.length > 0 && (
            <div className="panel-section">
              <h3>{t("entityDetail.relationships")}</h3>
              {related.map((relationship, index) => {
                const isOutgoing = relationship.source_ref === entity.ref;
                const otherRef = isOutgoing
                  ? relationship.target_ref
                  : relationship.source_ref;
                return (
                  <div className="rel-row" key={index}>
                    <span className="rel-arrow">{isOutgoing ? "→" : "←"}</span>
                    <span className="rel-type">{relationship.type}</span>
                    <span className="rel-title">{targetName(otherRef)}</span>
                    {relationship.reason && (
                      <span className="rel-reason">{relationship.reason}</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <p className="draft-preview-grounding">
            {entity.grounded_in.length > 0
              ? t("assistant.review.groundedIn", { count: entity.grounded_in.length })
              : t("assistant.review.newBadgeTitle")}
          </p>
        </div>
      </aside>
    </div>
  );
}
