import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { DraftEntity } from "../../api/agent";
import type { ImportReviewPayload } from "../../api/importJobs";
import { useImportJob } from "../../hooks/useImportJob";
import { translateApiError, translateWarning } from "../../i18n/eventText";
import { Icon } from "../ui/Icon";

interface ImportJobDialogProps {
  projectId: string;
  /** Knowledge-base source id, or a connection id when mode="connection". */
  sourceId: string;
  /** Filename, or the connection's name when mode="connection". */
  sourceFilename: string;
  /** "knowledge" (default) imports an uploaded file; "connection" migrates a
   * connected external tool's own content (backend IngestSource). Same
   * pipeline and review UI either way — only the start call differs. */
  mode?: "knowledge" | "connection";
  onClose: () => void;
}

const PHASE_LABEL_KEYS: Record<string, string> = {
  plan_windows: "import.phasePlanning",
  build_registry: "import.phaseRegistry",
  extract_windows: "import.phaseExtracting",
  merge_extractions: "import.phaseMerging",
  paginate_review: "import.phaseMerging",
};

export function ImportJobDialog({
  projectId,
  sourceId,
  sourceFilename,
  mode = "knowledge",
  onClose,
}: ImportJobDialogProps) {
  const { t } = useTranslation();
  const { job, progress, busy, error, start, startFromConnection, review, reset } =
    useImportJob(projectId);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function handleStart() {
    setStarted(true);
    if (mode === "connection") void startFromConnection(sourceId);
    else void start(sourceId);
  }

  function handleClose() {
    reset();
    onClose();
  }

  const status = job?.status ?? (started ? "extracting" : null);
  const title =
    mode === "connection" ? t("import.migrateDialogTitle") : t("import.dialogTitle");

  return (
    <div className="dialog-backdrop" onClick={handleClose}>
      <div
        className="dialog import-job-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{title}</h2>

        {!started && (
          <>
            <p>
              {mode === "connection"
                ? t("import.migrateConfirmBody", { name: sourceFilename })
                : t("import.confirmBody", { filename: sourceFilename })}
            </p>
            <div className="dialog-actions">
              <button type="button" className="button-secondary" onClick={handleClose}>
                {t("common.cancel")}
              </button>
              <button type="button" className="button-primary" onClick={handleStart}>
                {t("import.startButton")}
              </button>
            </div>
          </>
        )}

        {started && status && status !== "awaiting_review" && status !== "committed" && (
          <ImportProgressView
            status={status}
            progress={progress}
            totalWindows={job?.total_windows ?? 0}
          />
        )}

        {job?.status === "awaiting_review" && job.review && (
          <ImportReviewView
            review={job.review}
            busy={busy}
            currentSlice={job.current_slice}
            totalSlices={job.total_slices}
            committedSoFar={job.committed_entity_ids.length}
            onApprove={(draft) => void review({ action: "approve", draft })}
            onApproveAll={(draft) => void review({ action: "approve_all", draft })}
            onReject={() => void review({ action: "reject" })}
          />
        )}

        {job?.status === "committed" && (
          <>
            <p className="import-done-summary">
              <Icon name="check" size={16} />{" "}
              {t("import.doneSummary", { count: job.committed_entity_ids.length })}
            </p>
            <div className="dialog-actions">
              <button type="button" className="button-primary" onClick={handleClose}>
                {t("common.close")}
              </button>
            </div>
          </>
        )}

        {job?.status === "failed" && (
          <>
            <p className="error-text">{t("import.failed")}</p>
            <div className="dialog-actions">
              <button type="button" className="button-secondary" onClick={handleClose}>
                {t("common.close")}
              </button>
            </div>
          </>
        )}

        {error && <p className="error-text">{translateApiError(new Error(error), t)}</p>}
      </div>
    </div>
  );
}

function ImportProgressView({
  status,
  progress,
  totalWindows,
}: {
  status: string;
  progress: { phase: string; done: number; total: number } | null;
  totalWindows: number;
}) {
  const { t } = useTranslation();
  const phaseKey = PHASE_LABEL_KEYS[status] ?? "import.phasePlanning";
  return (
    <div className="import-progress">
      <p className="import-progress-phase">
        <span className="spinner" /> {t(phaseKey)}
      </p>
      {progress && (
        <p className="field-hint">
          {t("import.windowProgress", { done: progress.done, total: progress.total })}
        </p>
      )}
      {!progress && totalWindows > 0 && (
        <p className="field-hint">{t("import.totalWindows", { count: totalWindows })}</p>
      )}
    </div>
  );
}

function ImportReviewView({
  review,
  busy,
  currentSlice,
  totalSlices,
  committedSoFar,
  onApprove,
  onApproveAll,
  onReject,
}: {
  review: ImportReviewPayload;
  busy: boolean;
  currentSlice: number;
  totalSlices: number;
  committedSoFar: number;
  onApprove: (draft: { entities: DraftEntity[]; relationships: [] }) => void;
  onApproveAll: (draft: { entities: DraftEntity[]; relationships: [] }) => void;
  onReject: () => void;
}) {
  const { t } = useTranslation();
  const [entities, setEntities] = useState<DraftEntity[]>(review.draft.entities);
  const [removedRefs, setRemovedRefs] = useState<Set<string>>(new Set());

  useEffect(() => {
    setEntities(review.draft.entities);
    setRemovedRefs(new Set());
  }, [review]);

  function updateEntity(ref: string, patch: Partial<DraftEntity>) {
    setEntities((prev) => prev.map((e) => (e.ref === ref ? { ...e, ...patch } : e)));
  }

  function keptDraft(): { entities: DraftEntity[]; relationships: [] } {
    return {
      entities: entities.filter((e) => !removedRefs.has(e.ref)),
      relationships: [],
    };
  }

  const keptCount = entities.length - removedRefs.size;
  const uniqueNotes = new Map(
    review.merge_notes.map((note, index) => [
      `${note.code}-${index}`,
      translateWarning(note, t),
    ]),
  );

  return (
    <div className="assistant-review import-review">
      <p className="field-hint">
        {t("import.pageProgress", {
          current: currentSlice + 1,
          total: totalSlices,
        })}
        {committedSoFar > 0 &&
          ` — ${t("import.committedSoFar", { count: committedSoFar })}`}
      </p>

      {uniqueNotes.size > 0 && (
        <ul className="assistant-warnings">
          {[...uniqueNotes.entries()].map(([key, text]) => (
            <li key={key}>
              <Icon name="alert" size={13} /> {text}
            </li>
          ))}
        </ul>
      )}

      <div className="assistant-draft-entities">
        {entities.map((entity) => {
          const removed = removedRefs.has(entity.ref);
          return (
            <div
              key={entity.ref}
              className={
                removed ? "assistant-draft-entity removed" : "assistant-draft-entity"
              }
            >
              <div className="assistant-draft-entity-head">
                <label
                  className="assistant-draft-keep"
                  title={t("assistant.review.includeInCommitTitle")}
                >
                  <input
                    type="checkbox"
                    checked={!removed}
                    onChange={() =>
                      setRemovedRefs((prev) => {
                        const next = new Set(prev);
                        if (next.has(entity.ref)) next.delete(entity.ref);
                        else next.add(entity.ref);
                        return next;
                      })
                    }
                  />
                </label>
                <input
                  className="assistant-draft-title"
                  value={entity.title}
                  disabled={removed}
                  onChange={(e) => updateEntity(entity.ref, { title: e.target.value })}
                />
                <span className="assistant-draft-type">{entity.type}</span>
              </div>
              {!removed && (
                <textarea
                  rows={2}
                  value={entity.summary}
                  onChange={(e) =>
                    updateEntity(entity.ref, { summary: e.target.value })
                  }
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="assistant-review-actions">
        <button
          type="button"
          className="assistant-approve"
          disabled={busy || keptCount === 0}
          onClick={() => onApprove(keptDraft())}
        >
          {t("import.approvePage", { count: keptCount })}
        </button>
        <button
          type="button"
          className="button-secondary"
          disabled={busy || keptCount === 0}
          onClick={() => onApproveAll(keptDraft())}
          title={t("import.approveAllHint")}
        >
          {t("import.approveAll")}
        </button>
        <button
          type="button"
          className="assistant-reject"
          disabled={busy}
          onClick={onReject}
        >
          {t("import.rejectPage")}
        </button>
      </div>
    </div>
  );
}
