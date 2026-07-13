import type { ChangeEvent, KeyboardEvent } from "react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";

import type { KnowledgeSource, KnowledgeSourceStatus } from "../../api/types";
import { useFileDrop } from "../../hooks/useFileDrop";
import {
  useDeleteKnowledgeSource,
  useKnowledgeSources,
  useUploadKnowledgeSource,
} from "../../hooks/useKnowledge";
import { translateApiError } from "../../i18n/eventText";
import { Icon } from "../ui/Icon";

const ACCEPTED_EXTENSIONS =
  ".pdf,.txt,.md,.markdown,.json,.csv,.tsv,.yaml,.yml,.log";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Project's knowledge base: uploaded reference documents (rulebooks,
 * setting bibles) that ground both lore generation and the assistant's
 * search_knowledge_base chat tool. Separate from the world-canon entity
 * graph on purpose — see services/knowledge_index.py. */
export function KnowledgeBasePanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { data: sources, isLoading } = useKnowledgeSources(projectId);
  const upload = useUploadKnowledgeSource(projectId);
  const remove = useDeleteKnowledgeSource(projectId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function uploadFiles(files: File[]) {
    // Each file is its own upload — react-query's mutation state (pending/
    // error) reflects the most recent call, which is fine for the light
    // inline status this panel shows.
    for (const file of files) upload.mutate(file);
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length > 0) uploadFiles(files);
  }

  function handleDropzoneKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  }

  const { isDragging, dropHandlers } = useFileDrop(uploadFiles);

  return (
    <section className="settings-card knowledge-base-panel">
      <div className="settings-card-head">
        <h2>{t("knowledge.heading")}</h2>
        <p className="field-hint">{t("knowledge.hint")}</p>
      </div>

      <div
        className={`dropzone${isDragging ? " dropzone-active" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={handleDropzoneKeyDown}
        {...dropHandlers}
      >
        <div className="dropzone-icon" aria-hidden="true">
          <Icon name="upload" size={22} />
        </div>
        <p className="dropzone-title">
          {isDragging ? t("knowledge.dropzoneActive") : t("knowledge.dropzoneTitle")}
        </p>
        {!isDragging && (
          <p className="dropzone-subtitle">{t("knowledge.dropzoneSubtitle")}</p>
        )}
        {upload.isPending && (
          <p className="dropzone-status">{t("knowledge.uploading")}</p>
        )}
      </div>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS}
        onChange={handleFileChange}
        style={{ display: "none" }}
      />
      {upload.isError && (
        <p className="error-text">{translateApiError(upload.error, t)}</p>
      )}

      {isLoading && <p className="field-hint">{t("common.loading")}</p>}
      {sources?.length === 0 && (
        <p className="field-hint">{t("knowledge.noDocuments")}</p>
      )}

      <ul className="knowledge-source-list">
        {sources?.map((source) => (
          <KnowledgeSourceRow
            key={source.id}
            source={source}
            onRemove={() => remove.mutate(source.id)}
          />
        ))}
      </ul>
    </section>
  );
}

function KnowledgeSourceRow({
  source,
  onRemove,
}: {
  source: KnowledgeSource;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const statusLabels: Record<KnowledgeSourceStatus, string> = {
    pending: t("knowledge.statusPending"),
    processing: t("knowledge.statusProcessing"),
    ready: t("knowledge.statusReady"),
    failed: t("knowledge.statusFailed"),
  };

  return (
    <li className="knowledge-source-row">
      <span className="knowledge-source-name" title={source.original_filename}>
        {source.original_filename}
      </span>
      <span className="knowledge-source-meta">
        <span className={`knowledge-status-chip knowledge-status-${source.status}`}>
          {statusLabels[source.status]}
        </span>
        <span className="field-hint">{formatSize(source.size_bytes)}</span>
        {source.status === "ready" && (
          <span className="field-hint">
            {t("knowledge.chunksCount", { count: source.chunk_count })}
          </span>
        )}
        {source.status === "failed" && source.error && (
          <span
            className="error-text knowledge-source-error"
            title={source.error}
          >
            {source.error.slice(0, 80)}
          </span>
        )}
      </span>
      <button
        type="button"
        className="icon-button icon-button-danger knowledge-source-remove"
        onClick={onRemove}
        title={t("knowledge.deleteButton")}
        aria-label={t("knowledge.deleteButton")}
      >
        <Icon name="x" size={14} />
      </button>
    </li>
  );
}
