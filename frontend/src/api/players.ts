import { apiClient } from "./client";
import type { NetworkStatus, Player, PlayerCreated, PlayerNote } from "./types";

export const networkApi = {
  get: () => apiClient.get<NetworkStatus>("/api/network"),
};

// DM-side player management (loopback-only, like every other project route).
export const playersApi = {
  list: (projectId: string) =>
    apiClient.get<Player[]>(`/api/projects/${projectId}/players`),
  create: (projectId: string, name: string) =>
    apiClient.post<PlayerCreated>(`/api/projects/${projectId}/players`, { name }),
  rotate: (projectId: string, playerId: string) =>
    apiClient.post<PlayerCreated>(
      `/api/projects/${projectId}/players/${playerId}/rotate`,
    ),
  revoke: (projectId: string, playerId: string) =>
    apiClient.post<Player>(
      `/api/projects/${projectId}/players/${playerId}/revoke`,
    ),
  remove: (projectId: string, playerId: string) =>
    apiClient.delete<void>(`/api/projects/${projectId}/players/${playerId}`),
  notesForEntity: (projectId: string, entityId: string) =>
    apiClient.get<PlayerNote[]>(
      `/api/projects/${projectId}/entities/${entityId}/player-notes`,
    ),
};
