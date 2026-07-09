import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { entitiesApi } from "../api/entities";
import type { EntityCreate } from "../api/types";

export function useEntities(type?: string) {
  return useQuery({
    queryKey: ["entities", type],
    queryFn: () => entitiesApi.list(type),
  });
}

export function useCreateEntity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EntityCreate) => entitiesApi.create(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["entities"] });
    },
  });
}
