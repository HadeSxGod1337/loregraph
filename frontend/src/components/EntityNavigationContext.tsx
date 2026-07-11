import { createContext, useContext } from "react";
import { useMatch, useNavigate } from "react-router-dom";

/** How "go to entity X" behaves depends on where you are: the graph page
 * re-points its detail panel without changing the URL, everywhere else does a
 * router navigation. This context is the single entry point for both, so
 * things like wikilink chips work identically in every view. */
export const EntityNavigationContext = createContext<
  ((entityId: string) => void) | null
>(null);

export function useEntityNavigation(): (entityId: string) => void {
  const override = useContext(EntityNavigationContext);
  const navigate = useNavigate();
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;
  return (
    override ??
    ((entityId: string) => {
      if (projectId) navigate(`/projects/${projectId}/entities/${entityId}`);
    })
  );
}
