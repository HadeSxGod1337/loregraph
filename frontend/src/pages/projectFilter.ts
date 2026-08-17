import type { Project } from "../api/types";

/** Projects for the grid: the continue/last-opened project is pulled out
 * into its own card, and the rest are narrowed by the filter query. */
export function filterProjects(
  projects: Project[],
  excludeId: string | undefined,
  query: string,
): Project[] {
  const needle = query.trim().toLowerCase();
  return projects.filter(
    (p) => p.id !== excludeId && (needle === "" || p.name.toLowerCase().includes(needle)),
  );
}
