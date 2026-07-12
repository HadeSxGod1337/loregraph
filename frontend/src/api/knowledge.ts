import { apiClient } from "./client";
import type { KnowledgeSource } from "./types";

export const knowledgeApi = {
  list: (projectId: string) =>
    apiClient.get<KnowledgeSource[]>(`/api/projects/${projectId}/knowledge`),
  upload: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.postForm<KnowledgeSource>(
      `/api/projects/${projectId}/knowledge`,
      form,
    );
  },
  remove: (id: string) => apiClient.delete<void>(`/api/knowledge/${id}`),
};
