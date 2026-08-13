import { useCallback, useState } from "react";

/** Which folders the DM has collapsed in the entity list, per project.
 *
 * Only deviations are stored: a folder nobody touched is open, so switching
 * grouping on never hides rows that were visible a second ago. The state is
 * keyed by tree *position* (see pathKey), so an entity that sits in two
 * factions collapses independently in each. */
export interface TreeExpansion {
  isOpen: (key: string) => boolean;
  toggle: (key: string) => void;
  setMany: (keys: string[], open: boolean) => void;
}

function storageKey(projectId: string): string {
  return `loregraph:tree-open:${projectId}`;
}

function load(projectId: string): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(storageKey(projectId));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, boolean>;
    }
  } catch {
    // Corrupted or unavailable storage is not worth failing a page render
    // over — start from "everything open" instead.
  }
  return {};
}

export function useTreeExpansion(projectId: string): TreeExpansion {
  const [state, setState] = useState<Record<string, boolean>>(() => load(projectId));

  const persist = useCallback(
    (next: Record<string, boolean>) => {
      setState(next);
      try {
        localStorage.setItem(storageKey(projectId), JSON.stringify(next));
      } catch {
        // Private mode / quota: the tree still works for this session.
      }
    },
    [projectId],
  );

  const isOpen = useCallback((key: string) => state[key] ?? true, [state]);

  const toggle = useCallback(
    (key: string) => persist({ ...state, [key]: !(state[key] ?? true) }),
    [persist, state],
  );

  const setMany = useCallback(
    (keys: string[], open: boolean) => {
      const next = { ...state };
      for (const key of keys) next[key] = open;
      persist(next);
    },
    [persist, state],
  );

  return { isOpen, toggle, setMany };
}
