import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { knowledgeApi } from "../api/knowledge";
import type { KnowledgeSource } from "../api/types";

const POLL_INTERVAL_MS = 1500;

function hasUnsettledSource(sources: KnowledgeSource[] | undefined): boolean {
  return (sources ?? []).some(
    (s) => s.status === "pending" || s.status === "processing",
  );
}

export function useKnowledgeSources(projectId: string) {
  return useQuery({
    queryKey: ["knowledge", projectId],
    queryFn: () => knowledgeApi.list(projectId),
    // Ingestion runs as a background task after upload — poll while
    // anything is still pending/processing, like the assistant's own
    // status-node polling pattern elsewhere in the app.
    refetchInterval: (query) =>
      hasUnsettledSource(query.state.data) ? POLL_INTERVAL_MS : false,
  });
}

export function useUploadKnowledgeSource(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => knowledgeApi.upload(projectId, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge", projectId] });
    },
  });
}

export function useDeleteKnowledgeSource(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => knowledgeApi.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge", projectId] });
    },
  });
}
