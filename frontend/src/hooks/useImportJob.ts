import { useCallback, useRef, useState } from "react";

import {
  type ImportJob,
  type ImportJobEvent,
  type ImportJobProgressEvent,
  type ImportReviewDecision,
  importJobsApi,
} from "../api/importJobs";
import { useProjectEvent } from "./useProjectEvents";

export interface ImportJobProgress {
  phase: "registry" | "extract";
  done: number;
  total: number;
}

export interface ImportJobController {
  job: ImportJob | null;
  progress: ImportJobProgress | null;
  busy: boolean;
  error: string | null;
  start: (sourceId: string) => Promise<void>;
  review: (decision: ImportReviewDecision) => Promise<void>;
  reset: () => void;
}

/** Drives one bulk-import job (see backend agent/import_graph.py): start,
 * then zero or more review-page decisions, mirroring useAgentChat's shape
 * for the equivalent chat-turn flow. Fine-grained per-window progress
 * arrives over the project's WebSocket (job.progress, see
 * services/event_bus.py) — the SSE stream from start()/review() only
 * carries one `status` event per whole graph node, which doesn't show
 * individual windows finishing inside build_registry/extract_windows. */
export function useImportJob(projectId: string): ImportJobController {
  const [job, setJob] = useState<ImportJob | null>(null);
  const [progress, setProgress] = useState<ImportJobProgress | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const jobIdRef = useRef<string | null>(null);

  useProjectEvent<ImportJobProgressEvent>(projectId, "job.progress", (payload) => {
    if (payload.job_id === jobIdRef.current) {
      setProgress({ phase: payload.phase, done: payload.done, total: payload.total });
    }
  });

  const handleEvent = useCallback((event: ImportJobEvent) => {
    switch (event.type) {
      case "status":
        break;
      case "review":
        setProgress(null);
        setJob((prev) =>
          prev ? { ...prev, status: "awaiting_review", review: event.payload } : prev,
        );
        break;
      case "done":
        jobIdRef.current = event.job.job_id;
        setProgress(null);
        setJob(event.job);
        break;
      case "error":
        setError(event.detail);
        break;
    }
  }, []);

  const start = useCallback(
    async (sourceId: string) => {
      setBusy(true);
      setError(null);
      setProgress(null);
      setJob(null);
      jobIdRef.current = null;
      try {
        await importJobsApi.start(projectId, sourceId, handleEvent);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [projectId, handleEvent],
  );

  const review = useCallback(
    async (decision: ImportReviewDecision) => {
      if (!jobIdRef.current) return;
      setBusy(true);
      setError(null);
      try {
        await importJobsApi.review(projectId, jobIdRef.current, decision, handleEvent);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [projectId, handleEvent],
  );

  const reset = useCallback(() => {
    setJob(null);
    setProgress(null);
    setError(null);
    jobIdRef.current = null;
  }, []);

  return { job, progress, busy, error, start, review, reset };
}
