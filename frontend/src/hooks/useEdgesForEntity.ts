import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { edgesApi } from "../api/edges";
import type { EdgeCreate, EdgeUpdate } from "../api/types";

// Mirrors the same gap as entity mutations: the graph view reads from
// `["subgraph", ...]`, not `["edges", ...]` — invalidate both.
function invalidateEdgeCaches(
  queryClient: QueryClient,
  projectId: string,
  ...entityIds: string[]
) {
  for (const id of entityIds) {
    void queryClient.invalidateQueries({ queryKey: ["edges", projectId, id] });
  }
  void queryClient.invalidateQueries({ queryKey: ["edges", projectId] });
  void queryClient.invalidateQueries({ queryKey: ["subgraph", projectId] });
}

export function useEdgesForEntity(projectId: string, entityId: string | undefined) {
  return useQuery({
    queryKey: ["edges", projectId, entityId],
    queryFn: () => edgesApi.listForEntity(projectId, entityId!),
    enabled: entityId !== undefined,
  });
}

export function useCreateEdge(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EdgeCreate) => edgesApi.create(projectId, data),
    onSuccess: (edge) =>
      invalidateEdgeCaches(queryClient, projectId, edge.source_entity_id, edge.target_entity_id),
  });
}

export function useUpdateEdge(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: EdgeUpdate }) =>
      edgesApi.update(projectId, id, data),
    onSuccess: (edge) =>
      invalidateEdgeCaches(queryClient, projectId, edge.source_entity_id, edge.target_entity_id),
  });
}

export function useDeleteEdge(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => edgesApi.remove(projectId, id),
    onSuccess: () => invalidateEdgeCaches(queryClient, projectId),
  });
}
