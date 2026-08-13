import { useCallback, useState } from "react";

import { DEFAULT_HIERARCHY, type HierarchyConfig } from "../lib/hierarchy";

/** What an edge type means for the folder tree: nothing, "source holds
 * target" (`contains`), or "source belongs to target" (`member_of`). */
export type HierarchyRole = "none" | "forward" | "inverse";

function storageKey(projectId: string): string {
  return `loregraph:hierarchy-types:${projectId}`;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function load(projectId: string): HierarchyConfig {
  try {
    const raw = localStorage.getItem(storageKey(projectId));
    if (!raw) return DEFAULT_HIERARCHY;
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed === "object" &&
      isStringArray((parsed as HierarchyConfig).forward) &&
      isStringArray((parsed as HierarchyConfig).inverse)
    ) {
      return parsed as HierarchyConfig;
    }
  } catch {
    // Unreadable settings fall back to the defaults rather than to no
    // grouping at all — the list must render either way.
  }
  return DEFAULT_HIERARCHY;
}

/** Which relationship types this project reads as containment.
 *
 * Vocabulary is per project (a DM may write `sworn_to` where another writes
 * `member_of`), so this is a setting rather than a constant. It lives in
 * localStorage for now: it describes how this browser draws the list, and
 * moving it onto the project record is a backend migration of its own. */
export function useHierarchyConfig(projectId: string) {
  const [config, setConfig] = useState<HierarchyConfig>(() => load(projectId));

  const persist = useCallback(
    (next: HierarchyConfig) => {
      setConfig(next);
      try {
        localStorage.setItem(storageKey(projectId), JSON.stringify(next));
      } catch {
        // Session-only is still better than refusing the change.
      }
    },
    [projectId],
  );

  const roleOf = useCallback(
    (type: string): HierarchyRole => {
      if (config.forward.includes(type)) return "forward";
      if (config.inverse.includes(type)) return "inverse";
      return "none";
    },
    [config],
  );

  const setRole = useCallback(
    (type: string, role: HierarchyRole) => {
      persist({
        forward: [
          ...config.forward.filter((item) => item !== type),
          ...(role === "forward" ? [type] : []),
        ],
        inverse: [
          ...config.inverse.filter((item) => item !== type),
          ...(role === "inverse" ? [type] : []),
        ],
      });
    },
    [config, persist],
  );

  const reset = useCallback(() => persist(DEFAULT_HIERARCHY), [persist]);

  const isDefault =
    JSON.stringify(config) === JSON.stringify(DEFAULT_HIERARCHY);

  return { config, roleOf, setRole, reset, isDefault };
}
