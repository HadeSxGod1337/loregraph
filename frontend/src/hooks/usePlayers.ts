import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { playersApi } from "../api/players";

export function usePlayers(projectId: string) {
  return useQuery({
    queryKey: ["players", projectId],
    queryFn: () => playersApi.list(projectId),
  });
}

export function useCreatePlayer(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => playersApi.create(projectId, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["players", projectId] });
    },
  });
}

export function useRotatePlayer(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (playerId: string) => playersApi.rotate(projectId, playerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["players", projectId] });
    },
  });
}

export function useRevokePlayer(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (playerId: string) => playersApi.revoke(projectId, playerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["players", projectId] });
    },
  });
}

export function useDeletePlayer(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (playerId: string) => playersApi.remove(projectId, playerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["players", projectId] });
    },
  });
}
