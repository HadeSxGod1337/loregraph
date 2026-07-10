import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { entitiesApi } from "../api/entities";
import type { EntityUpdate } from "../api/types";

// The graph view's nodes come from a separate `["subgraph", ...]` query, not
// `["entities", ...]` — any entity mutation that should be visible on the
// graph canvas (title/fields/icon changes) has to invalidate both caches.
function invalidateEntityCaches(
  queryClient: QueryClient,
  projectId: string,
  entityId?: string,
) {
  if (entityId) {
    void queryClient.invalidateQueries({
      queryKey: ["entities", "detail", projectId, entityId],
    });
  }
  void queryClient.invalidateQueries({ queryKey: ["entities", projectId] });
  void queryClient.invalidateQueries({ queryKey: ["subgraph", projectId] });
}

export function useEntity(projectId: string, id: string | undefined) {
  return useQuery({
    queryKey: ["entities", "detail", projectId, id],
    queryFn: () => entitiesApi.get(projectId, id!),
    enabled: id !== undefined,
  });
}

export function useUpdateEntity(projectId: string, id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EntityUpdate) => entitiesApi.update(projectId, id, data),
    onSuccess: () => invalidateEntityCaches(queryClient, projectId, id),
  });
}

export function useDeleteEntity(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => entitiesApi.remove(projectId, id),
    onSuccess: () => invalidateEntityCaches(queryClient, projectId),
  });
}

export function useSetEntityIcon(projectId: string, entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) =>
      entitiesApi.setIcon(projectId, entityId, attachmentId),
    onSuccess: () => invalidateEntityCaches(queryClient, projectId, entityId),
  });
}

export function useClearEntityIcon(projectId: string, entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => entitiesApi.clearIcon(projectId, entityId),
    onSuccess: () => invalidateEntityCaches(queryClient, projectId, entityId),
  });
}
