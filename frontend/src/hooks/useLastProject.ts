import { useEffect } from "react";
import { useMatch } from "react-router-dom";

const STORAGE_KEY = "loregraph:lastProject";

/** Remembers which project you were in, so "/" can offer to continue.
 *
 * Local to the browser on purpose: which world you had open is a property of
 * this machine and this person, not of the campaign data — putting it on the
 * server would mean two DMs on the same LAN fighting over one value. */
export function useLastProject(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

/** Records the open project. Mounted once, in the layout — every route under
 * /projects/:id passes through it. */
export function useRememberLastProject(): void {
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;

  useEffect(() => {
    if (projectId) localStorage.setItem(STORAGE_KEY, projectId);
  }, [projectId]);
}
