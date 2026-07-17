import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { connectionsApi } from "../api/connections";
import type {
  ConnectionCreate,
  ConnectionUpdate,
  ExportRequest,
  ImportRequest,
} from "../api/types";

export function useConnectorTypes() {
  return useQuery({
    queryKey: ["connectorTypes"],
    queryFn: () => connectionsApi.listTypes(),
  });
}

export function useConnections(projectId: string) {
  return useQuery({
    queryKey: ["connections", projectId],
    queryFn: () => connectionsApi.list(projectId),
  });
}

export function useCreateConnection(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ConnectionCreate) => connectionsApi.create(projectId, data),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["connections", projectId] }),
  });
}

export function useUpdateConnection(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ConnectionUpdate }) =>
      connectionsApi.update(projectId, id, data),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["connections", projectId] }),
  });
}

export function useDeleteConnection(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => connectionsApi.remove(projectId, id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["connections", projectId] }),
  });
}

export function useTestConnection(projectId: string) {
  return useMutation({
    mutationFn: (connectionId: string) => connectionsApi.test(projectId, connectionId),
  });
}

export function useExportPreview(projectId: string) {
  return useMutation({
    mutationFn: ({ connectionId, request }: { connectionId: string; request?: ExportRequest }) =>
      connectionsApi.previewExport(projectId, connectionId, request),
  });
}

export function useRunExport(projectId: string) {
  return useMutation({
    mutationFn: ({ connectionId, request }: { connectionId: string; request?: ExportRequest }) =>
      connectionsApi.export(projectId, connectionId, request),
  });
}

export function useRunImport(projectId: string) {
  return useMutation({
    mutationFn: ({ connectionId, request }: { connectionId: string; request?: ImportRequest }) =>
      connectionsApi.import(projectId, connectionId, request),
  });
}
