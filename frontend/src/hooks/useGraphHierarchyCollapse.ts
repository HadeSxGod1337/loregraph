import { useCallback, useEffect, useState } from "react";

/** Which entities the graph view has collapsed — visual-only, per project.
 *
 * Deliberately keyed by entity id, not tree path like `useTreeExpansion`: on
 * the graph, one entity is one node no matter how many hierarchy parents it
 * has, so there is exactly one collapse state to track per id, not one per
 * position. See `computeHierarchyVisibility` in `lib/hierarchy.ts` for how
 * multiple open/closed ancestors combine into what's actually on screen. */
export interface GraphHierarchyCollapse {
  collapsedIds: ReadonlySet<string>;
  isCollapsed: (entityId: string) => boolean;
  toggle: (entityId: string) => void;
  collapseAll: (entityIds: Iterable<string>) => void;
  expandAll: () => void;
}

function storageKey(projectId: string): string {
  return `loregraph:graph-collapsed:${projectId}`;
}

function load(projectId: string): Set<string> {
  try {
    const raw = localStorage.getItem(storageKey(projectId));
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((item) => typeof item === "string")) {
      return new Set(parsed);
    }
  } catch {
    // Corrupted or unavailable storage is not worth failing the canvas over
    // — start fully expanded instead, same as a first-ever visit.
  }
  return new Set();
}

export function useGraphHierarchyCollapse(projectId: string): GraphHierarchyCollapse {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => load(projectId));

  // GraphViewPage reuses one component instance across projects (no `key=`,
  // see its own projectId-reset effect) — without this, switching projects
  // would keep showing the previous project's collapsed branches until a
  // full page reload.
  useEffect(() => {
    setCollapsedIds(load(projectId));
  }, [projectId]);

  const persist = useCallback(
    (next: Set<string>) => {
      setCollapsedIds(next);
      try {
        localStorage.setItem(storageKey(projectId), JSON.stringify([...next]));
      } catch {
        // Private mode / quota: collapse state still works for this session.
      }
    },
    [projectId],
  );

  const isCollapsed = useCallback(
    (entityId: string) => collapsedIds.has(entityId),
    [collapsedIds],
  );

  const toggle = useCallback(
    (entityId: string) => {
      const next = new Set(collapsedIds);
      if (next.has(entityId)) next.delete(entityId);
      else next.add(entityId);
      persist(next);
    },
    [collapsedIds, persist],
  );

  const collapseAll = useCallback(
    (entityIds: Iterable<string>) => persist(new Set(entityIds)),
    [persist],
  );

  const expandAll = useCallback(() => persist(new Set()), [persist]);

  return { collapsedIds, isCollapsed, toggle, collapseAll, expandAll };
}
