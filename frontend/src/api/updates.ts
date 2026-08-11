import { apiClient } from "./client";
import type { UpdatePreferences, UpdateStatus } from "./types";

export const updatesApi = {
  get: () => apiClient.get<UpdateStatus>("/api/updates"),
  setPreferences: (prefs: UpdatePreferences) =>
    apiClient.put<UpdatePreferences>("/api/updates/preferences", prefs),
};
