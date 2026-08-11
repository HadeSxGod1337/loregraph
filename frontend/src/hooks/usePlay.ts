import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { playApi } from "../api/play";
import type { PlayerNoteWrite } from "../api/types";

// Live-ish at the table without a websocket: poll on an interval and on focus,
// so a card the DM reveals mid-session shows up within a few seconds.
const PLAY_REFETCH = { refetchInterval: 15_000, refetchOnWindowFocus: true };

export function usePlayEntities(enabled: boolean) {
  return useQuery({
    queryKey: ["play", "entities"],
    queryFn: () => playApi.entities(),
    enabled,
    ...PLAY_REFETCH,
  });
}

export function usePlayEntity(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["play", "entity", id],
    queryFn: () => playApi.entity(id!),
    enabled: enabled && id !== undefined,
    ...PLAY_REFETCH,
  });
}

export function usePlayGraph(enabled: boolean) {
  return useQuery({
    queryKey: ["play", "graph"],
    queryFn: () => playApi.graph(),
    enabled,
    ...PLAY_REFETCH,
  });
}

export function usePlayNotes(entityId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["play", "notes", entityId],
    queryFn: () => playApi.notes(entityId!),
    enabled: enabled && entityId !== undefined,
    ...PLAY_REFETCH,
  });
}

export function usePlayCreateNote(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PlayerNoteWrite) => playApi.createNote(entityId, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["play", "notes", entityId] });
    },
  });
}

export function usePlayUpdateNote(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, data }: { noteId: string; data: PlayerNoteWrite }) =>
      playApi.updateNote(noteId, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["play", "notes", entityId] });
    },
  });
}

export function usePlayDeleteNote(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noteId: string) => playApi.deleteNote(noteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["play", "notes", entityId] });
    },
  });
}
