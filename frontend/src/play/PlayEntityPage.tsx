import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { API_URL } from "../api/client";
import type { EntityField, ProseMirrorDoc } from "../api/types";
import { RichTextView } from "../components/entity/RichTextView";
import { usePlayEntity } from "../hooks/usePlay";
import { PlayNotesPanel } from "./PlayNotesPanel";

function fieldPreview(field: EntityField, empty: string): string {
  switch (field.field_type) {
    case "tag":
      return (field.value as string[]).join(", ") || empty;
    case "boolean":
      return field.value ? "✓" : "—";
    case "attachment":
      return "";
    default:
      return String(field.value);
  }
}

export function PlayEntityPage() {
  const { t } = useTranslation();
  const { token, id } = useParams<{ token: string; id: string }>();
  const { data: entity, isLoading, isError } = usePlayEntity(id, true);

  if (isLoading) return <p className="play-empty">{t("play.loading")}</p>;
  // A card that was hidden again mid-session 404s — send the player back.
  if (isError || !entity) {
    return (
      <div className="play-empty">
        <p>{t("play.cardGone")}</p>
        <Link to={`/play/${token}`}>{t("play.backToCards")}</Link>
      </div>
    );
  }

  return (
    <article className="play-entity">
      <Link to={`/play/${token}`} className="play-back">
        ← {t("play.backToCards")}
      </Link>

      <header className="play-entity-head">
        {entity.icon && (
          <img className="play-entity-icon" src={API_URL + entity.icon.url} alt="" />
        )}
        <div>
          <span className="entity-type-badge">{entity.type}</span>
          <h1>{entity.title}</h1>
        </div>
      </header>

      {entity.player_text && (
        <section className="play-entity-text">
          <RichTextView value={entity.player_text} />
        </section>
      )}

      {entity.fields.length > 0 && (
        <section className="play-entity-fields">
          {entity.fields.map((f) => (
            <div className="field-line" key={f.key}>
              <span className="k">{f.key}</span>
              {f.field_type === "rich_text" ? (
                <div className="v v-rich-text">
                  <RichTextView value={f.value as ProseMirrorDoc} />
                </div>
              ) : (
                <span className="v">{fieldPreview(f, t("play.emptyValue"))}</span>
              )}
            </div>
          ))}
        </section>
      )}

      <PlayNotesPanel entityId={entity.id} />
    </article>
  );
}
