import { createContext, useContext } from "react";

/** The selected entity id, read directly by `EntityNode` instead of being
 * threaded through each node's `data` — with hundreds of nodes on canvas,
 * baking `isSelected` into `data` would force the whole node array to be
 * rebuilt (new object identity per node) on every selection change. Reading
 * it from context means only the previously- and newly-selected nodes
 * actually re-render. */
export const SelectedEntityContext = createContext<string | null>(null);

export function useSelectedEntity(): string | null {
  return useContext(SelectedEntityContext);
}
