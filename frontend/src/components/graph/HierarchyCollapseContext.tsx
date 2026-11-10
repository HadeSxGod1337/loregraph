import { createContext, useContext } from "react";

export interface HierarchyCollapseState {
  /** Entity ids that have at least one hierarchy child in the current base
   * view — governs whether a node gets a collapse control at all. */
  parentIds: ReadonlySet<string>;
  /** Entity ids currently collapsed (their hierarchy children are hidden). */
  collapsedIds: ReadonlySet<string>;
  /** Collapsed id → how many of its descendants ended up hidden as a result.
   * Missing/absent means "collapsed but hiding nothing right now" (e.g. an
   * open path through another parent still shows everything underneath). */
  hiddenCounts: ReadonlyMap<string, number>;
  onToggle: (entityId: string) => void;
}

const EMPTY_SET: ReadonlySet<string> = new Set();
const EMPTY_MAP: ReadonlyMap<string, number> = new Map();

const DEFAULT_STATE: HierarchyCollapseState = {
  parentIds: EMPTY_SET,
  collapsedIds: EMPTY_SET,
  hiddenCounts: EMPTY_MAP,
  onToggle: () => {},
};

/** Per-node hierarchy collapse info, read directly by `EntityNode` — same
 * shape as `SelectedEntityContext`/`ActiveRootContext`/`HoveredEntityContext`:
 * auxiliary UI state a node needs at render time that has nothing to do with
 * its position, kept out of `data` so `toFlowNode`/`useSyncedFlowNodes` stay
 * unaware hierarchy collapse exists at all — GraphCanvas's node-sync
 * plumbing only ever deals in the *filtered* nodes/edges arrays it's given. */
export const HierarchyCollapseContext =
  createContext<HierarchyCollapseState>(DEFAULT_STATE);

export function useHierarchyCollapse(): HierarchyCollapseState {
  return useContext(HierarchyCollapseContext);
}
