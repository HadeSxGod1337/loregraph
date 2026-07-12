import type { ChangeEvent } from "react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";

import type { KnowledgeSource, KnowledgeSourceStatus } from "../../api/types";
import {
  useDeleteKnowledgeSource,
  useKnowledgeSources,
  useUploadKnowledgeSource,
} from "../../hooks/useKnowledge";
import { translateApiError } from "../../i18n/eventText";

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

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) upload.mutate(file);
  }

  return (
    <div className="knowledge-base-panel">
      <h2>{t("knowledge.heading")}</h2>
      <p className="field-hint">{t("knowledge.hint")}</p>

      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={upload.isPending}
      >
        {upload.isPending ? t("knowledge.uploading") : t("knowledge.uploadButton")}
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.md,.markdown,.json,.csv,.tsv,.yaml,.yml,.log"
        onChange={handleFileChange}
        style={{ display: "none" }}
      />
      {upload.isError && (
        <p className="error-text">{translateApiError(upload.error, t)}</p>
      )}

      {isLoading && <p>{t("common.loading")}</p>}
      {sources?.length === 0 && <p className="field-hint">{t("knowledge.noDocuments")}</p>}

      <ul className="knowledge-source-list">
        {sources?.map((source) => (
          <KnowledgeSourceRow
            key={source.id}
            source={source}
            onRemove={() => remove.mutate(source.id)}
          />
        ))}
      </ul>
    </div>
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
      <span className="knowledge-source-name">{source.original_filename}</span>
      <span className="knowledge-source-status">{statusLabels[source.status]}</span>
      <span className="field-hint">{formatSize(source.size_bytes)}</span>
      {source.status === "ready" && (
        <span className="field-hint">
          {t("knowledge.chunksCount", { count: source.chunk_count })}
        </span>
      )}
      {source.status === "failed" && source.error && (
        <span className="error-text" title={source.error}>
          {source.error.slice(0, 80)}
        </span>
      )}
      <button type="button" className="button-danger" onClick={onRemove}>
        {t("knowledge.deleteButton")}
      </button>
    </li>
  );
}
