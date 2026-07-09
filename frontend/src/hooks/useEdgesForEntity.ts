import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { edgesApi } from "../api/edges";
import type { EdgeCreate, EdgeUpdate } from "../api/types";

// Mirrors the same gap as entity mutations: the graph view reads from
// `["subgraph", ...]`, not `["edges", ...]` — invalidate both.
function invalidateEdgeCaches(queryClient: QueryClient, ...entityIds: string[]) {
  for (const id of entityIds) {
    void queryClient.invalidateQueries({ queryKey: ["edges", id] });
  }
  void queryClient.invalidateQueries({ queryKey: ["edges"] });
  void queryClient.invalidateQueries({ queryKey: ["subgraph"] });
}

export function useEdgesForEntity(entityId: string | undefined) {
  return useQuery({
    queryKey: ["edges", entityId],
    queryFn: () => edgesApi.listForEntity(entityId!),
    enabled: entityId !== undefined,
  });
}

export function useCreateEdge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EdgeCreate) => edgesApi.create(data),
    onSuccess: (edge) =>
      invalidateEdgeCaches(queryClient, edge.source_entity_id, edge.target_entity_id),
  });
}

export function useUpdateEdge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: EdgeUpdate }) =>
      edgesApi.update(id, data),
    onSuccess: (edge) =>
      invalidateEdgeCaches(queryClient, edge.source_entity_id, edge.target_entity_id),
  });
}

export function useDeleteEdge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => edgesApi.remove(id),
    onSuccess: () => invalidateEdgeCaches(queryClient),
  });
}
