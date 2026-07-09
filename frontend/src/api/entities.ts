import { apiClient } from "./client";
import type { Entity, EntityCreate, EntityUpdate } from "./types";

export const entitiesApi = {
  list: (type?: string) => apiClient.get<Entity[]>("/api/entities", { type }),
  get: (id: string) => apiClient.get<Entity>(`/api/entities/${id}`),
  create: (data: EntityCreate) => apiClient.post<Entity>("/api/entities", data),
  update: (id: string, data: EntityUpdate) =>
    apiClient.put<Entity>(`/api/entities/${id}`, data),
  remove: (id: string) => apiClient.delete<void>(`/api/entities/${id}`),
  setIcon: (id: string, attachmentId: string) =>
    apiClient.put<Entity>(`/api/entities/${id}/icon`, { attachment_id: attachmentId }),
  clearIcon: (id: string) => apiClient.delete<Entity>(`/api/entities/${id}/icon`),
};
