import { apiClient } from "./client";
import type { Project, ProjectCreate, ProjectExport, ProjectUpdate } from "./types";

export const projectsApi = {
  list: () => apiClient.get<Project[]>("/api/projects"),
  get: (id: string) => apiClient.get<Project>(`/api/projects/${id}`),
  create: (data: ProjectCreate) => apiClient.post<Project>("/api/projects", data),
  update: (id: string, data: ProjectUpdate) =>
    apiClient.put<Project>(`/api/projects/${id}`, data),
  remove: (id: string) => apiClient.delete<void>(`/api/projects/${id}`),
  export: (id: string) => apiClient.get<ProjectExport>(`/api/projects/${id}/export`),
  import: (data: ProjectExport) =>
    apiClient.post<Project>("/api/projects/import", data),
  // The vector index is derived data (rebuilt from SQLite, the source of
  // truth) — self-serve recovery when search/the assistant can't find an
  // entity that visibly exists, without needing shell access to curl the
  // backend directly.
  reindex: (id: string) =>
    apiClient.post<{ indexed: number }>(`/api/projects/${id}/reindex`),
};
