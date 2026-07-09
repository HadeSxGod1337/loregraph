import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { entitiesApi } from "../api/entities";
import type { EntityUpdate } from "../api/types";

// The graph view's nodes come from a separate `["subgraph", ...]` query, not
// `["entities", ...]` — any entity mutation that should be visible on the
// graph canvas (title/fields/icon changes) has to invalidate both caches.
function invalidateEntityCaches(queryClient: QueryClient, entityId?: string) {
  if (entityId) {
    void queryClient.invalidateQueries({ queryKey: ["entities", "detail", entityId] });
  }
  void queryClient.invalidateQueries({ queryKey: ["entities"] });
  void queryClient.invalidateQueries({ queryKey: ["subgraph"] });
}

export function useEntity(id: string | undefined) {
  return useQuery({
    queryKey: ["entities", "detail", id],
    queryFn: () => entitiesApi.get(id!),
    enabled: id !== undefined,
  });
}

export function useUpdateEntity(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EntityUpdate) => entitiesApi.update(id, data),
    onSuccess: () => invalidateEntityCaches(queryClient, id),
  });
}

export function useDeleteEntity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => entitiesApi.remove(id),
    onSuccess: () => invalidateEntityCaches(queryClient),
  });
}

export function useSetEntityIcon(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) => entitiesApi.setIcon(entityId, attachmentId),
    onSuccess: () => invalidateEntityCaches(queryClient, entityId),
  });
}

export function useClearEntityIcon(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => entitiesApi.clearIcon(entityId),
    onSuccess: () => invalidateEntityCaches(queryClient, entityId),
  });
}
