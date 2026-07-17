import { apiClient } from "./client";
import type {
  Connection,
  ConnectionCreate,
  ConnectionUpdate,
  ConnectorType,
  ExportPreview,
  ExportRequest,
  ExportResult,
  ImportRequest,
  ImportResult,
  ProbeResult,
} from "./types";

export const connectionsApi = {
  listTypes: () => apiClient.get<ConnectorType[]>("/api/connectors"),

  list: (projectId: string) =>
    apiClient.get<Connection[]>(`/api/projects/${projectId}/connections`),

  create: (projectId: string, data: ConnectionCreate) =>
    apiClient.post<Connection>(`/api/projects/${projectId}/connections`, data),

  update: (projectId: string, connectionId: string, data: ConnectionUpdate) =>
    apiClient.put<Connection>(
      `/api/projects/${projectId}/connections/${connectionId}`,
      data,
    ),

  remove: (projectId: string, connectionId: string) =>
    apiClient.delete<void>(
      `/api/projects/${projectId}/connections/${connectionId}`,
    ),

  test: (projectId: string, connectionId: string) =>
    apiClient.post<ProbeResult>(
      `/api/projects/${projectId}/connections/${connectionId}/test`,
    ),

  previewExport: (
    projectId: string,
    connectionId: string,
    request: ExportRequest = {},
  ) =>
    apiClient.post<ExportPreview>(
      `/api/projects/${projectId}/connections/${connectionId}/export/preview`,
      request,
    ),

  export: (projectId: string, connectionId: string, request: ExportRequest = {}) =>
    apiClient.post<ExportResult>(
      `/api/projects/${projectId}/connections/${connectionId}/export`,
      request,
    ),

  import: (projectId: string, connectionId: string, request: ImportRequest = {}) =>
    apiClient.post<ImportResult>(
      `/api/projects/${projectId}/connections/${connectionId}/import`,
      request,
    ),
};
