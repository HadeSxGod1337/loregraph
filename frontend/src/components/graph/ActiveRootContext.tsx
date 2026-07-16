import { createContext, useContext } from "react";

/** The graph's current root/active entity id, read directly by `EntityNode`
 * instead of being threaded through each node's `data` — same rationale as
 * `SelectedEntityContext`. Changing root (the "Active entity" picker in All
 * mode, "Set as root", double-click) must not rebuild every node's object
 * identity just to move the "root" indicator from one card to another. */
export const ActiveRootContext = createContext<string>("");

export function useActiveRoot(): string {
  return useContext(ActiveRootContext);
}
