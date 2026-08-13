import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { API_URL } from "../../api/client";
import type { Entity } from "../../api/types";
import { typeColor, typeSoftBackground } from "../../lib/typeColor";
import { Icon } from "../ui/Icon";

interface EntityTreeRowProps {
  projectId: string;
  entity: Entity;
  /** More than zero turns the row into a folder: clicking it opens the group
   * instead of the card, and the card gets its own ↗ button. */
  childCount?: number;
  /** Types of the members, for the dots that preview a collapsed folder. */
  memberTypes?: string[];
  open?: boolean;
  onToggle?: () => void;
  /** True when the row is only on screen as the way to a matching member. */
  context?: boolean;
  /** Number of folders holding this entity — above one, the row says so,
   * because the same entity then appears in several places at once. */
  parentCount?: number;
}

/** One line of the entity list, as a leaf or as a folder.
 *
 * The inside of the row (avatar, title, subtitle, type badge) is identical in
 * both cases and identical to the ungrouped list — grouping must not make a
 * row look like a different kind of thing. */
export function EntityTreeRow({
  projectId,
  entity,
  childCount = 0,
  memberTypes = [],
  open = false,
  onToggle,
  context = false,
  parentCount = 0,
}: EntityTreeRowProps) {
  const { t } = useTranslation();
  const className = [
    "entity-list-item",
    "entity-tree-item",
    childCount > 0 ? "is-folder" : "",
    context ? "is-context" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const body = (
    <>
      <EntityAvatar entity={entity} />
      <span className="entity-list-main">
        <span className="entity-list-title">{entity.title}</span>
        <EntitySubtitle entity={entity} />
      </span>
      {parentCount > 1 && (
        <span className="entity-tree-parents" title={t("entities.inFoldersHint")}>
          {t("entities.inFolders", { count: parentCount })}
        </span>
      )}
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
    </>
  );

  if (childCount === 0) {
    return (
      <Link to={`/projects/${projectId}/entities/${entity.id}`} className={className}>
        {body}
      </Link>
    );
  }

  return (
    <div
      className={className}
      style={{ borderLeftColor: typeColor(entity.type) }}
      onClick={onToggle}
    >
      <span className={open ? "entity-tree-chevron is-open" : "entity-tree-chevron"}>
        <Icon name="chevron-down" size={14} />
      </span>
      {body}
      {!open && memberTypes.length > 0 && (
        <span className="entity-tree-dots" aria-hidden="true">
          {memberTypes.slice(0, 5).map((type) => (
            <span
              key={type}
              className="entity-tree-dot"
              style={{ background: typeColor(type) }}
            />
          ))}
        </span>
      )}
      <span className="entity-tree-count">{childCount}</span>
      <Link
        to={`/projects/${projectId}/entities/${entity.id}`}
        className="entity-tree-open"
        title={t("entities.openCard")}
        aria-label={t("entities.openCard")}
        onClick={(event) => event.stopPropagation()}
      >
        <Icon name="external-link" size={14} />
      </Link>
    </div>
  );
}

function EntityAvatar({ entity }: { entity: Entity }) {
  if (entity.icon) {
    return <img className="entity-avatar" src={API_URL + entity.icon.url} alt="" />;
  }
  return (
    <span
      className="entity-avatar"
      style={{
        background: typeSoftBackground(entity.type),
        color: typeColor(entity.type),
      }}
    >
      {entity.title.trim().charAt(0).toUpperCase()}
    </span>
  );
}

function EntitySubtitle({ entity }: { entity: Entity }) {
  const { t } = useTranslation();
  const text = entitySubtitle(entity, t);
  if (!text) return null;
  return <span className="entity-list-sub">{text}</span>;
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
