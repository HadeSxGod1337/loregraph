import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { API_URL } from "../api/client";
import { typeColor, typeSoftBackground } from "../lib/typeColor";
import { usePlayEntities } from "../hooks/usePlay";

/** The revealed cards, as a grid. Everything here already passed the server's
 * filter — the client never had the hidden ones. */
export function PlayEntityListPage() {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const { data: entities, isLoading } = usePlayEntities(true);

  if (isLoading) return <p className="play-empty">{t("play.loading")}</p>;
  if (!entities || entities.length === 0) {
    return <p className="play-empty">{t("play.noCards")}</p>;
  }

  return (
    <div className="play-card-grid">
      {entities.map((entity) => (
        <Link
          key={entity.id}
          to={`/play/${token}/entity/${entity.id}`}
          className="play-card"
          style={{ "--type-color": typeColor(entity.type) } as React.CSSProperties}
        >
          {entity.icon && (
            <img className="play-card-icon" src={API_URL + entity.icon.url} alt="" />
          )}
          <div className="play-card-info">
            <span
              className="entity-type-badge"
              style={{
                background: typeSoftBackground(entity.type),
                color: typeColor(entity.type),
                borderColor: "transparent",
              }}
            >
              {entity.type}
            </span>
            <span className="play-card-title">{entity.title}</span>
          </div>
        </Link>
      ))}
    </div>
  );
}
