import { apiClient } from "./client";
import type {
  PlayerEntity,
  PlayerNote,
  PlayerNoteWrite,
  PlayerSubgraph,
  PlaySession,
} from "./types";

// The player-facing API. Authenticated by the session cookie set at
// startSession; the project is taken from the token server-side, never passed
// here. Every response is already filtered to what this player may see.
export const playApi = {
  startSession: (token: string) =>
    apiClient.post<PlaySession>("/api/play/session", { token }),
  endSession: () => apiClient.delete<void>("/api/play/session"),
  me: () => apiClient.get<PlaySession>("/api/play/me"),
  entities: () => apiClient.get<PlayerEntity[]>("/api/play/entities"),
  entity: (id: string) =>
    apiClient.get<PlayerEntity>(`/api/play/entities/${id}`),
  graph: () => apiClient.get<PlayerSubgraph>("/api/play/graph"),
  notes: (entityId: string) =>
    apiClient.get<PlayerNote[]>(`/api/play/entities/${entityId}/notes`),
  createNote: (entityId: string, data: PlayerNoteWrite) =>
    apiClient.post<PlayerNote>(`/api/play/entities/${entityId}/notes`, data),
  updateNote: (noteId: string, data: PlayerNoteWrite) =>
    apiClient.put<PlayerNote>(`/api/play/notes/${noteId}`, data),
  deleteNote: (noteId: string) =>
    apiClient.delete<void>(`/api/play/notes/${noteId}`),
};
