import { apiClient } from "./client";
import type { Entity, EntityCreate, EntityUpdate } from "./types";

export const entitiesApi = {
  list: (projectId: string, type?: string) =>
    apiClient.get<Entity[]>(`/api/projects/${projectId}/entities`, { type }),
  get: (projectId: string, id: string) =>
    apiClient.get<Entity>(`/api/projects/${projectId}/entities/${id}`),
  create: (projectId: string, data: EntityCreate) =>
    apiClient.post<Entity>(`/api/projects/${projectId}/entities`, data),
  update: (projectId: string, id: string, data: EntityUpdate) =>
    apiClient.put<Entity>(`/api/projects/${projectId}/entities/${id}`, data),
  remove: (projectId: string, id: string) =>
    apiClient.delete<void>(`/api/projects/${projectId}/entities/${id}`),
  setIcon: (projectId: string, id: string, attachmentId: string) =>
    apiClient.put<Entity>(`/api/projects/${projectId}/entities/${id}/icon`, {
      attachment_id: attachmentId,
    }),
  clearIcon: (projectId: string, id: string) =>
    apiClient.delete<Entity>(`/api/projects/${projectId}/entities/${id}/icon`),
};
