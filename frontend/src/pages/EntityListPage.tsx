import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import type { Entity } from "../api/types";
import { EntityTree } from "../components/entity/EntityTree";
import { EntityTreeRow } from "../components/entity/EntityTreeRow";
import { CharacterSheetImportButton } from "../components/integrations/CharacterSheetImportButton";
import { TemplatePickerDialog } from "../components/sheet/TemplatePickerDialog";
import { Icon } from "../components/ui/Icon";
import { SkeletonList } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import {
  useAllEdges,
  useCreateEdge,
  useDeleteEdge,
} from "../hooks/useEdgesForEntity";
import { useEntities } from "../hooks/useEntities";
import { useHierarchyConfig } from "../hooks/useHierarchyConfig";
import { useTreeExpansion } from "../hooks/useTreeExpansion";
import { translateApiError } from "../i18n/eventText";
import {
  buildForest,
  buildHierarchy,
  filterForest,
  folderKeys,
  wouldCycle,
} from "../lib/hierarchy";
import { typeColor } from "../lib/typeColor";

/** How the list is arranged. "links" reads the containment edges of the
 * project and nests members under their faction/location; the other two are
 * escape hatches for when that grouping is not what the DM is looking for. */
type ListMode = "links" | "type" | "flat";

const LIST_MODES: ListMode[] = ["links", "type", "flat"];

function modeStorageKey(projectId: string): string {
  return `loregraph:list-mode:${projectId}`;
}

function loadMode(projectId: string): ListMode {
  const saved = localStorage.getItem(modeStorageKey(projectId));
  return LIST_MODES.includes(saved as ListMode) ? (saved as ListMode) : "links";
}

export function EntityListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [picking, setPicking] = useState(false);
  const [mode, setMode] = useState<ListMode>(() => loadMode(projectId!));
  const {
    data: entities,
    isLoading: entitiesLoading,
    error,
  } = useEntities(projectId!);
  const { data: edges, isLoading: edgesLoading } = useAllEdges(projectId!);
  const expansion = useTreeExpansion(projectId!);
  const { config: hierarchyConfig } = useHierarchyConfig(projectId!);
  const pushToast = useToast();
  const createEdge = useCreateEdge(projectId!);
  const deleteEdge = useDeleteEdge(projectId!);

  // Types come from the data itself — the user picks from chips instead of
  // typing a type name from memory into a text filter.
  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const entity of entities ?? []) {
      counts.set(entity.type, (counts.get(entity.type) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [entities]);

  const query = search.trim().toLowerCase();
  const matches = useMemo(
    () => (entity: Entity) =>
      (typeFilter === null || entity.type === typeFilter) &&
      (query === "" || entity.title.toLowerCase().includes(query)),
    [typeFilter, query],
  );

  /** The flat set of hits — what the counters and the empty states talk
   * about, so the numbers stay about entities and not about tree rows (an
   * entity in two factions is one hit shown twice). */
  const visible = useMemo(
    () => (entities ?? []).filter(matches),
    [entities, matches],
  );

  const hierarchy = useMemo(
    () => buildHierarchy(edges ?? [], hierarchyConfig),
    [edges, hierarchyConfig],
  );
  const forest = useMemo(
    () => buildForest(entities ?? [], hierarchy),
    [entities, hierarchy],
  );
  const treeNodes = useMemo(() => filterForest(forest, matches), [forest, matches]);
  const groupsByType = useMemo(() => groupByType(visible), [visible]);

  const isLoading = entitiesLoading || edgesLoading;
  const hasEntities = (entities?.length ?? 0) > 0;
  const isFiltering = query !== "" || typeFilter !== null;
  const canGroup = hierarchy.hasAny || typeCounts.length > 1;
  const allFolders = useMemo(() => folderKeys(treeNodes), [treeNodes]);
  const anyOpen = allFolders.some((key) => expansion.isOpen(key));

  const chooseMode = (next: ListMode) => {
    setMode(next);
    localStorage.setItem(modeStorageKey(projectId!), next);
  };

  /* Dragging a row into a folder writes a real relationship into the graph —
     the same edge the entity page would create, not a list-only arrangement.
     Hence the checks up front and the undo in the toast: it is a canon edit,
     even though it looks like sorting a list. */
  /* Undefined when the DM has turned every "A holds B" type off: there is
     then no edge a drop could honestly create, so rows stop dragging. */
  const nestingEdgeType: string | undefined = hierarchyConfig.forward[0];

  const canNest = (childId: string, parentId: string): boolean =>
    !wouldCycle(hierarchy, parentId, childId) &&
    !(hierarchy.parentsOf.get(childId) ?? []).includes(parentId);

  const nest = (childId: string, parentId: string) => {
    const child = entities?.find((entity) => entity.id === childId);
    const parent = entities?.find((entity) => entity.id === parentId);
    if (!child || !parent) return;
    const names = { child: child.title, parent: parent.title };

    if ((hierarchy.parentsOf.get(childId) ?? []).includes(parentId)) {
      pushToast(t("entities.nestAlready", names));
      return;
    }
    if (wouldCycle(hierarchy, parentId, childId)) {
      pushToast(t("entities.nestCycle", names), "error");
      return;
    }

    createEdge.mutate(
      {
        source_entity_id: parentId,
        target_entity_id: childId,
        // The project's own word for containment, so a drop writes the same
        // vocabulary the DM and the agent already use here.
        type: nestingEdgeType!,
        label: null,
      },
      {
        onSuccess: (edge) =>
          pushToast(t("entities.nested", names), "success", {
            label: t("common.undo"),
            onClick: () => deleteEdge.mutate(edge.id),
          }),
        onError: (mutationError) =>
          pushToast(translateApiError(mutationError, t), "error"),
      },
    );
  };

  return (
    <div className="entity-list-page">
      <div className="entity-list-header">
        <h1>{t("entities.title")}</h1>
        <div className="entity-list-header-actions">
          <CharacterSheetImportButton projectId={projectId!} />
          <button
            type="button"
            className="button-ghost"
            onClick={() => setPicking(true)}
          >
            <Icon name="layers" />
            {t("sheet.newFromTemplate")}
          </button>
          <Link to={`/projects/${projectId}/entities/new`} className="button-primary">
            <Icon name="plus" />
            {t("entities.newEntity")}
          </Link>
        </div>
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
          {canGroup && (
            <div className="entity-list-modes">
              <div className="segmented" role="group" aria-label={t("entities.groupBy")}>
                {LIST_MODES.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={mode === option ? "active" : undefined}
                    aria-pressed={mode === option}
                    onClick={() => chooseMode(option)}
                  >
                    {t(`entities.group_${option}`)}
                  </button>
                ))}
              </div>
              {mode === "links" && allFolders.length > 0 && (
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => expansion.setMany(allFolders, !anyOpen)}
                >
                  {t(anyOpen ? "entities.collapseAll" : "entities.expandAll")}
                </button>
              )}
              {isFiltering && hasEntities && (
                <span className="entity-list-count">
                  {t("entities.shownOfTotal", {
                    shown: visible.length,
                    total: entities?.length ?? 0,
                  })}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {isLoading && <SkeletonList rows={5} />}
      {error && <p className="error-text">{translateApiError(error, t)}</p>}

      {!isLoading && visible.length > 0 && mode === "links" && (
        <EntityTree
          projectId={projectId!}
          nodes={treeNodes}
          expansion={expansion}
          forceOpen={query !== ""}
          onNest={nestingEdgeType ? nest : undefined}
          canNest={canNest}
        />
      )}

      {!isLoading && visible.length > 0 && mode === "type" && (
        <div className="entity-type-groups">
          {groupsByType.map(([type, group]) => (
            <section key={type} className="entity-type-group">
              <h2 className="entity-type-group-header">
                <span
                  className="type-chip-dot"
                  style={{ background: typeColor(type) }}
                />
                {type}
                <span className="type-chip-count">{group.length}</span>
              </h2>
              <ul className="entity-list">
                {group.map((entity) => (
                  <li key={entity.id}>
                    <EntityTreeRow projectId={projectId!} entity={entity} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {!isLoading && visible.length > 0 && mode === "flat" && (
        <ul className="entity-list">
          {visible.map((entity) => (
            <li key={entity.id}>
              <EntityTreeRow projectId={projectId!} entity={entity} />
            </li>
          ))}
        </ul>
      )}

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
      {!isLoading && hasEntities && visible.length === 0 && (
        <p>{t("entities.noMatches")}</p>
      )}

      {picking && (
        <TemplatePickerDialog
          projectId={projectId!}
          onClose={() => setPicking(false)}
          onCreated={(entityId) =>
            navigate(`/projects/${projectId}/entities/${entityId}`)
          }
        />
      )}
    </div>
  );
}

/** Sections for the "by type" mode, biggest type first — the same order the
 * filter chips above the list already use. */
function groupByType(entities: Entity[]): [string, Entity[]][] {
  const groups = new Map<string, Entity[]>();
  for (const entity of entities) {
    const group = groups.get(entity.type);
    if (group) group.push(entity);
    else groups.set(entity.type, [entity]);
  }
  return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
}
