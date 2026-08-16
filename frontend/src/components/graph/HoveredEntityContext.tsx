import { createContext, useContext } from "react";

/** The entity id currently under the pointer, or null — read directly by
 * `FloatingEdge` instead of being threaded through the `edges` array, same
 * rationale as `SelectedEntityContext`/`ActiveRootContext`. Changes on every
 * node mouse-enter/leave, so keeping it out of `data` matters even more here:
 * baking it into each edge's data would rebuild the whole edges array on
 * every hover transition instead of leaving edge object identity alone. */
export const HoveredEntityContext = createContext<string | null>(null);

export function useHoveredEntity(): string | null {
  return useContext(HoveredEntityContext);
}
