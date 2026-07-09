import { apiClient } from "./client";
import type { Attachment } from "./types";

export const attachmentsApi = {
  listForEntity: (entityId: string) =>
    apiClient.get<Attachment[]>(`/api/entities/${entityId}/attachments`),
  upload: (entityId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.postForm<Attachment>(`/api/entities/${entityId}/attachments`, form);
  },
  remove: (id: string) => apiClient.delete<void>(`/api/attachments/${id}`),
};
