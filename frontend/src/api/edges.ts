import { apiClient } from "./client";
import type { Edge, EdgeCreate, EdgeUpdate } from "./types";

export const edgesApi = {
  listForEntity: (entityId: string) =>
    apiClient.get<Edge[]>("/api/edges", { entity_id: entityId }),
  create: (data: EdgeCreate) => apiClient.post<Edge>("/api/edges", data),
  update: (id: string, data: EdgeUpdate) =>
    apiClient.put<Edge>(`/api/edges/${id}`, data),
  remove: (id: string) => apiClient.delete<void>(`/api/edges/${id}`),
};
