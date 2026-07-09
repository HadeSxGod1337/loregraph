import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { attachmentsApi } from "../api/attachments";

export function useAttachments(entityId: string | undefined) {
  return useQuery({
    queryKey: ["attachments", entityId],
    queryFn: () => attachmentsApi.listForEntity(entityId!),
    enabled: entityId !== undefined,
  });
}

export function useUploadAttachment(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => attachmentsApi.upload(entityId, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["attachments", entityId] });
    },
  });
}

export function useDeleteAttachment(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => attachmentsApi.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["attachments", entityId] });
    },
  });
}
