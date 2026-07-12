import type { ChangeEvent } from "react";
import { useRef } from "react";

import type { KnowledgeSource, KnowledgeSourceStatus } from "../../api/types";
import {
  useDeleteKnowledgeSource,
  useKnowledgeSources,
  useUploadKnowledgeSource,
} from "../../hooks/useKnowledge";

const STATUS_LABELS: Record<KnowledgeSourceStatus, string> = {
  pending: "⏳ В очереди",
  processing: "⏳ Обрабатывается",
  ready: "✅ Готово",
  failed: "❌ Ошибка",
};

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
      <h2>База знаний проекта</h2>
      <p className="field-hint">
        Загрузи справочные документы (правила, книга игрока, краткое описание
        вселенной — PDF, .txt, .md). Ассистент использует их при генерации
        лора и может искать по ним в чате, но они не становятся каноном мира.
      </p>

      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={upload.isPending}
      >
        {upload.isPending ? "Загружаю…" : "+ Загрузить документ"}
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
        onChange={handleFileChange}
        style={{ display: "none" }}
      />
      {upload.isError && (
        <p className="error-text">{(upload.error as Error).message}</p>
      )}

      {isLoading && <p>Loading...</p>}
      {sources?.length === 0 && (
        <p className="field-hint">Документов пока нет.</p>
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
  return (
    <li className="knowledge-source-row">
      <span className="knowledge-source-name">{source.original_filename}</span>
      <span className="knowledge-source-status">
        {STATUS_LABELS[source.status]}
      </span>
      <span className="field-hint">{formatSize(source.size_bytes)}</span>
      {source.status === "ready" && (
        <span className="field-hint">{source.chunk_count} чанков</span>
      )}
      {source.status === "failed" && source.error && (
        <span className="error-text" title={source.error}>
          {source.error.slice(0, 80)}
        </span>
      )}
      <button type="button" className="button-danger" onClick={onRemove}>
        Удалить
      </button>
    </li>
  );
}
