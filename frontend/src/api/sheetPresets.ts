import { apiClient } from "./client";
import type { SheetPreset, SheetPresetCreate } from "./types";

export const sheetPresetsApi = {
  list: (projectId: string) =>
    apiClient.get<SheetPreset[]>(`/api/projects/${projectId}/sheet-presets`),
  create: (projectId: string, data: SheetPresetCreate) =>
    apiClient.post<SheetPreset>(`/api/projects/${projectId}/sheet-presets`, data),
  remove: (projectId: string, id: string) =>
    apiClient.delete<void>(`/api/projects/${projectId}/sheet-presets/${id}`),
};
