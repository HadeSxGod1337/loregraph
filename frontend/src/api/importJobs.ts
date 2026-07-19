import { apiClient, streamSse } from "./client";
import type { AgentWarning, DraftEntity, LoreDraft } from "./agent";

// Mirrors backend schemas/import_job.py — one contract, used verbatim.

export type ImportJobStatus =
  | "planning"
  | "extracting"
  | "awaiting_review"
  | "committing"
  | "committed"
  | "failed";

export interface ImportReviewPayload {
  slice_index: number;
  total_slices: number;
  draft: LoreDraft;
  merge_notes: AgentWarning[];
  warnings: AgentWarning[];
  input_tokens: number;
  output_tokens: number;
}

export interface ImportJob {
  job_id: string;
  project_id: string;
  source_id: string;
  source_filename: string;
  status: ImportJobStatus;
  total_windows: number;
  total_slices: number;
  current_slice: number;
  committed_entity_ids: string[];
  input_tokens: number;
  output_tokens: number;
  review: ImportReviewPayload | null;
  created_at: string;
  updated_at: string;
}

export interface ImportReviewDecision {
  action: "approve" | "reject" | "approve_all";
  draft?: LoreDraft | null;
}

export type ImportJobEvent =
  | { type: "status"; node: string }
  | { type: "review"; payload: ImportReviewPayload }
  | { type: "done"; job: ImportJob }
  | { type: "error"; code?: string; detail: string };

/** Progress pushed on the project's WebSocket channel (see backend
 * services/event_bus.py EVENT_JOB_PROGRESS) as individual windows finish —
 * finer-grained than the SSE `status` event, which only fires once per
 * whole graph node (a node's internal fan-out is otherwise invisible). */
export interface ImportJobProgressEvent {
  job_id: string;
  phase: "registry" | "extract";
  done: number;
  total: number;
}

export const importJobsApi = {
  start: (
    projectId: string,
    sourceId: string,
    onEvent: (event: ImportJobEvent) => void,
  ) =>
    streamSse<ImportJobEvent>(
      `/api/projects/${projectId}/import-jobs`,
      { source_id: sourceId },
      onEvent,
    ),
  review: (
    projectId: string,
    jobId: string,
    decision: ImportReviewDecision,
    onEvent: (event: ImportJobEvent) => void,
  ) =>
    streamSse<ImportJobEvent>(
      `/api/projects/${projectId}/import-jobs/${jobId}/review`,
      decision,
      onEvent,
    ),
  list: (projectId: string) =>
    apiClient.get<ImportJob[]>(`/api/projects/${projectId}/import-jobs`),
  detail: (projectId: string, jobId: string) =>
    apiClient.get<ImportJob>(`/api/projects/${projectId}/import-jobs/${jobId}`),
};

export type { DraftEntity };
