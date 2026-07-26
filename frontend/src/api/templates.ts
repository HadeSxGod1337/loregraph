import { apiClient } from "./client";
import type {
  Entity,
  EntityTemplate,
  EntityTemplateCreate,
  EntityTemplateUpdate,
} from "./types";

export const templatesApi = {
  list: (projectId: string) =>
    apiClient.get<EntityTemplate[]>(`/api/projects/${projectId}/templates`),
  get: (projectId: string, id: string) =>
    apiClient.get<EntityTemplate>(`/api/projects/${projectId}/templates/${id}`),
  create: (projectId: string, data: EntityTemplateCreate) =>
    apiClient.post<EntityTemplate>(`/api/projects/${projectId}/templates`, data),
  update: (projectId: string, id: string, data: EntityTemplateUpdate) =>
    apiClient.put<EntityTemplate>(
      `/api/projects/${projectId}/templates/${id}`,
      data,
    ),
  remove: (projectId: string, id: string) =>
    apiClient.delete<void>(`/api/projects/${projectId}/templates/${id}`),
  instantiate: (projectId: string, id: string, title: string) =>
    apiClient.post<Entity>(
      `/api/projects/${projectId}/templates/${id}/instantiate`,
      { title },
    ),
};
