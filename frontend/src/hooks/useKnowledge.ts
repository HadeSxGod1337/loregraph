import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { knowledgeApi } from "../api/knowledge";
import type { KnowledgeSource, KnowledgeSourceStatus } from "../api/types";
import { useProjectEvent } from "./useProjectEvents";

const POLL_INTERVAL_MS = 1500;

interface KnowledgeIngestStatusPayload {
  source_id: string;
  status: KnowledgeSourceStatus;
  chunk_count?: number;
  error?: string;
}

function hasUnsettledSource(sources: KnowledgeSource[] | undefined): boolean {
  return (sources ?? []).some(
    (s) => s.status === "pending" || s.status === "processing",
  );
}

export function useKnowledgeSources(projectId: string) {
  const queryClient = useQueryClient();
  const queryKey = ["knowledge", projectId];

  // Realtime updates (see backend services/event_bus.py /
  // services/knowledge_ingest.py) patch the cached row directly — no full
  // refetch needed for the common case. The refetchInterval below is only a
  // fallback for a dropped/reconnecting socket (useProjectEvent retries with
  // backoff on its own, but this keeps the UI eventually-correct either way).
  useProjectEvent<KnowledgeIngestStatusPayload>(
    projectId,
    "knowledge.ingest_status",
    (payload) => {
      queryClient.setQueryData<KnowledgeSource[]>(queryKey, (sources) =>
        sources?.map((source) =>
          source.id === payload.source_id
            ? {
                ...source,
                status: payload.status,
                chunk_count: payload.chunk_count ?? source.chunk_count,
                error: payload.error ?? null,
              }
            : source,
        ),
      );
    },
  );

  return useQuery({
    queryKey,
    queryFn: () => knowledgeApi.list(projectId),
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
