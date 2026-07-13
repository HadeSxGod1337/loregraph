import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { API_URL } from "../api/client";
import type { Entity } from "../api/types";
import { Icon } from "../components/ui/Icon";
import { SkeletonList } from "../components/ui/Skeleton";
import { useEntities } from "../hooks/useEntities";
import { translateApiError } from "../i18n/eventText";
import { typeColor, typeSoftBackground } from "../lib/typeColor";

export function EntityListPage() {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const { data: entities, isLoading, error } = useEntities(projectId!);

  // Types come from the data itself — the user picks from chips instead of
  // typing a type name from memory into a text filter.
  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const entity of entities ?? []) {
      counts.set(entity.type, (counts.get(entity.type) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [entities]);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (entities ?? []).filter(
      (entity) =>
        (typeFilter === null || entity.type === typeFilter) &&
        (query === "" || entity.title.toLowerCase().includes(query)),
    );
  }, [entities, typeFilter, search]);

  const hasEntities = (entities?.length ?? 0) > 0;

  return (
    <div className="entity-list-page">
      <div className="entity-list-header">
        <h1>{t("entities.title")}</h1>
        <Link to={`/projects/${projectId}/entities/new`} className="button-primary">
          <Icon name="plus" />
          {t("entities.newEntity")}
        </Link>
      </div>

      {hasEntities && (
        <div className="entity-list-toolbar">
          <input
            placeholder={t("entities.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="entity-list-filter"
          />
          {typeCounts.length > 1 && (
            <div className="type-chip-row">
              <button
                type="button"
                className={typeFilter === null ? "type-chip active" : "type-chip"}
                onClick={() => setTypeFilter(null)}
              >
                {t("entities.allTypes")}
                <span className="type-chip-count">{entities?.length}</span>
              </button>
              {typeCounts.map(([type, count]) => (
                <button
                  key={type}
                  type="button"
                  className={typeFilter === type ? "type-chip active" : "type-chip"}
                  onClick={() => setTypeFilter(typeFilter === type ? null : type)}
                >
                  <span
                    className="type-chip-dot"
                    style={{ background: typeColor(type) }}
                  />
                  {type}
                  <span className="type-chip-count">{count}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {isLoading && <SkeletonList rows={5} />}
      {error && <p className="error-text">{translateApiError(error, t)}</p>}

      <ul className="entity-list">
        {visible.map((entity) => (
          <li key={entity.id}>
            <EntityRow projectId={projectId!} entity={entity} />
          </li>
        ))}
      </ul>

      {!isLoading && !hasEntities && (
        <div className="empty-state">
          <p>{t("entities.noEntities")}</p>
          <div className="empty-state-actions">
            <Link
              to={`/projects/${projectId}/entities/new`}
              className="button-primary"
            >
              <Icon name="plus" />
              {t("entities.newEntity")}
            </Link>
          </div>
        </div>
      )}
      {hasEntities && visible.length === 0 && <p>{t("entities.noMatches")}</p>}
    </div>
  );
}

function EntityRow({ projectId, entity }: { projectId: string; entity: Entity }) {
  const { t } = useTranslation();
  const color = typeColor(entity.type);
  const subtitle = entitySubtitle(entity, t);
  return (
    <Link
      to={`/projects/${projectId}/entities/${entity.id}`}
      className="entity-list-item"
    >
      {entity.icon ? (
        <img className="entity-avatar" src={API_URL + entity.icon.url} alt="" />
      ) : (
        <span
          className="entity-avatar"
          style={{ background: typeSoftBackground(entity.type), color }}
        >
          {entity.title.trim().charAt(0).toUpperCase()}
        </span>
      )}
      <span className="entity-list-main">
        <span className="entity-list-title">{entity.title}</span>
        {subtitle && <span className="entity-list-sub">{subtitle}</span>}
      </span>
      <span
        className="entity-type-badge"
        style={{ background: typeSoftBackground(entity.type), color, borderColor: "transparent" }}
      >
        {entity.type}
      </span>
    </Link>
  );
}

/** Second line of a row: the first short text field marked for the graph
 * card (the entity's own "tagline"), else a field count. */
function entitySubtitle(
  entity: Entity,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const preview = entity.fields.find(
    (field) =>
      field.show_on_card &&
      field.field_type === "text" &&
      typeof field.value === "string" &&
      field.value.trim() !== "",
  );
  if (preview) return preview.value as string;
  const firstText = entity.fields.find(
    (field) =>
      field.field_type === "text" &&
      typeof field.value === "string" &&
      field.value.trim() !== "",
  );
  if (firstText) return firstText.value as string;
  if (entity.fields.length > 0) {
    return t("entities.fieldCount", { count: entity.fields.length });
  }
  return "";
}
