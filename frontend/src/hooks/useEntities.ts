import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { entitiesApi } from "../api/entities";
import type { EntityCreate } from "../api/types";

export function useEntities(projectId: string, type?: string) {
  return useQuery({
    queryKey: ["entities", projectId, type],
    queryFn: () => entitiesApi.list(projectId, type),
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
