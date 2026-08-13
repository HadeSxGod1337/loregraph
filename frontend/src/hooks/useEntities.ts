import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { entitiesApi } from "../api/entities";
import type { EntityCreate } from "../api/types";

// projectId may be undefined for callers that render outside a project (the
// command palette lives in the sidebar, which is also shown on "/"); the
// query simply doesn't run until there is one.
export function useEntities(projectId: string | undefined, type?: string) {
  return useQuery({
    queryKey: ["entities", projectId, type],
    queryFn: () => entitiesApi.list(projectId!, type),
    enabled: projectId !== undefined,
  });
}

export function useCreateEntity(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EntityCreate) => entitiesApi.create(projectId, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["entities", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["subgraph", projectId] });
    },
  });
}
