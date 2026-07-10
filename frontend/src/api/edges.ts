import { apiClient } from "./client";
import type { Edge, EdgeCreate, EdgeUpdate } from "./types";

export const edgesApi = {
  listForEntity: (projectId: string, entityId: string) =>
    apiClient.get<Edge[]>(`/api/projects/${projectId}/edges`, { entity_id: entityId }),
  create: (projectId: string, data: EdgeCreate) =>
    apiClient.post<Edge>(`/api/projects/${projectId}/edges`, data),
  update: (projectId: string, id: string, data: EdgeUpdate) =>
    apiClient.put<Edge>(`/api/projects/${projectId}/edges/${id}`, data),
  remove: (projectId: string, id: string) =>
    apiClient.delete<void>(`/api/projects/${projectId}/edges/${id}`),
};
