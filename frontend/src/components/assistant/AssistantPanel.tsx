import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AgentReviewPayload, DraftEntity, LoreDraft } from "../../api/agent";
import { ApiError, apiClient } from "../../api/client";
import type { Edge, Entity } from "../../api/types";
import {
  type AgentChat,
  useAgentChat,
  useAgentConfig,
  useAgentSessions,
} from "../../hooks/useAgent";
import { useEntities } from "../../hooks/useEntities";
import { translateEvent, translateWarning } from "../../i18n/eventText";

interface AssistantPanelProps {
  projectId: string;
  /** Called with created entity ids after an approved commit — the graph
   * page uses it to focus the freshly generated web. */
  onCommitted?: (entityIds: string[]) => void;
}

/** Conversational co-author: chat about the world (grounded answers), get
 * clarifying questions back, and review whole lore batches inline — with
 * per-stage progress and token streaming. */
export function AssistantPanel({ projectId, onCommitted }: AssistantPanelProps) {
  const { t } = useTranslation();
  const { data: config, error: configError } = useAgentConfig();
  const { data: entities } = useEntities(projectId);
  const chat = useAgentChat(projectId, onCommitted);

  if (configError instanceof ApiError && configError.status === 404) {
    return (
      <div className="assistant-onboarding">
        <h2>{t("assistant.onboarding.restartHeading")}</h2>
        <p>{t("assistant.onboarding.restartBody")}</p>
        <pre>{`cd backend
uv sync
uv run uvicorn loregraph.main:app --reload`}</pre>
      </div>
    );
  }
  if (config && !config.llm_configured) {
    return <OnboardingCard provider={config.llm_provider} />;
  }

  return (
    <div className="assistant-panel">
      <SessionPicker projectId={projectId} chat={chat} />
      <Transcript chat={chat} entities={entities ?? []} />
      <ChatInput chat={chat} entities={entities ?? []} projectId={projectId} />
    </div>
  );
}

function SessionPicker({ projectId, chat }: { projectId: string; chat: AgentChat }) {
  const { t } = useTranslation();
  const { data: sessions } = useAgentSessions(projectId);
  const recent = (sessions ?? []).filter((s) => s.title).slice(0, 8);
  if (recent.length === 0 && !chat.threadId) return null;
  return (
    <div className="assistant-session-picker">
      <select
        value={chat.threadId ?? ""}
        onChange={(e) => {
          if (e.target.value) void chat.openSession(e.target.value);
        }}
      >
        <option value="">{t("assistant.historyPlaceholder")}</option>
        {recent.map((session) => (
          <option key={session.thread_id} value={session.thread_id}>
            [{t(`assistant.status.${session.status}` as const)}]{" "}
            {session.title.slice(0, 60)}
          </option>
        ))}
      </select>
      {chat.threadId && (
        <button
          type="button"
          onClick={chat.reset}
          title={t("assistant.newConversation")}
        >
          {t("assistant.newConversationButton")}
        </button>
      )}
    </div>
  );
}

function Transcript({
  chat,
  entities,
}: {
  chat: AgentChat;
  entities: Entity[];
}) {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.messages, chat.statusNode, chat.pendingReview]);

  const isEmpty =
    chat.messages.length === 0 && !chat.pendingReview && !chat.busy;

  return (
    <div className="assistant-transcript">
      {isEmpty && (
        <p className="assistant-empty-invite">
          {entities.length === 0
            ? t("assistant.emptyInviteEmptyWorld")
            : t("assistant.emptyInviteHasWorld")}
        </p>
      )}
      {chat.messages.map((message, index) => (
        <div
          key={`${index}-${message.role}`}
          className={`assistant-bubble assistant-bubble-${message.role}`}
        >
          {message.attachments.length > 0 && (
            <div className="assistant-attachment-chips">
              {message.attachments.map((filename) => (
                <span key={filename} className="assistant-attachment-chip">
                  📎 {filename}
                </span>
              ))}
            </div>
          )}
          {message.event_code
            ? translateEvent(message.event_code, message.event_params ?? {}, message.text, t)
            : message.text}
        </div>
      ))}
      {chat.statusNode && (
        <div className="assistant-status-line">
          {t([`assistant.stage.${chat.statusNode}`, "assistant.stage.fallback"], {
            node: chat.statusNode,
          })}
        </div>
      )}
      {chat.pendingReview?.draft && (
        <ReviewCard
          review={chat.pendingReview}
          entities={entities}
          busy={chat.busy}
          onDecision={(action, draft, feedback) =>
            void chat.review({ action, draft, feedback })
          }
        />
      )}
      {chat.error && <p className="assistant-error">{chat.error}</p>}
      <div ref={bottomRef} />
    </div>
  );
}

function ChatInput({
  chat,
  entities,
  projectId,
}: {
  chat: AgentChat;
  entities: Entity[];
  projectId: string;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [anchorId, setAnchorId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // While a draft awaits review, new messages are rejected by the backend —
  // block them in the UI too, with an explanation.
  const reviewPending = chat.pendingReview !== null;
  const blocked = chat.busy || reviewPending;

  function submit() {
    const trimmed = text.trim();
    if (!trimmed || blocked) return;
    setText("");
    setFiles([]);
    void chat.send(trimmed, anchorId || null, files);
  }

  function handleFilesPicked(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (picked.length > 0) setFiles((prev) => [...prev, ...picked]);
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  return (
    <div className="assistant-chat-input">
      <SuggestionHints
        projectId={projectId}
        entities={entities}
        onPick={(hint) => {
          setText(hint.instruction);
          setAnchorId(hint.anchorId ?? "");
        }}
      />
      {files.length > 0 && (
        <div className="assistant-attachment-chips">
          {files.map((file, index) => (
            <span key={`${file.name}-${index}`} className="assistant-attachment-chip">
              📎 {file.name}
              <button
                type="button"
                className="assistant-attachment-remove"
                onClick={() => removeFile(index)}
                title={t("assistant.removeFileTitle")}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <textarea
        rows={2}
        placeholder={
          reviewPending
            ? t("assistant.inputPlaceholderBlocked")
            : t("assistant.inputPlaceholderDefault")
        }
        value={text}
        disabled={blocked}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className="assistant-input-row">
        {entities.length > 0 && (
          <select
            value={anchorId}
            title={t("assistant.anchorTitle")}
            onChange={(e) => setAnchorId(e.target.value)}
          >
            <option value="">{t("assistant.anchorWholeWorld")}</option>
            {entities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.title}
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          disabled={blocked}
          title={t("assistant.attachTitle")}
          onClick={() => fileInputRef.current?.click()}
        >
          📎
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/jpeg,image/png,image/gif,image/webp,.pdf,.txt,.md,.markdown,.json,.csv,.tsv,.yaml,.yml,.log"
          onChange={handleFilesPicked}
          style={{ display: "none" }}
        />
        <button type="button" disabled={!text.trim() || blocked} onClick={submit}>
          {chat.busy ? t("assistant.sending") : t("assistant.sendButton")}
        </button>
      </div>
    </div>
  );
}

function OnboardingCard({ provider }: { provider: string }) {
  const { t } = useTranslation();
  return (
    <div className="assistant-onboarding">
      <h2>{t("assistant.onboarding.setupHeading")}</h2>
      <p>
        {t("assistant.onboarding.setupBody1", { provider })}{" "}
        <code>{provider}</code>
      </p>
      <p>{t("assistant.onboarding.setupBody2")}</p>
      <pre>
        {`# Anthropic (default)
CAMPAIGN_ANTHROPIC_API_KEY=sk-ant-...

# or OpenAI
CAMPAIGN_LLM_PROVIDER=openai
CAMPAIGN_OPENAI_API_KEY=sk-...
CAMPAIGN_LLM_MODEL_GENERATION=gpt-...

# or fully local via Ollama (no key, lower quality)
CAMPAIGN_LLM_PROVIDER=ollama
CAMPAIGN_LLM_MODEL_GENERATION=llama3
CAMPAIGN_LLM_MODEL_EXTRACTION=llama3
CAMPAIGN_LLM_MODEL_COMPOSITION=llama3`}
      </pre>
      <p>{t("assistant.onboarding.setupBody3")}</p>
    </div>
  );
}

interface Hint {
  text: string;
  instruction: string;
  anchorId?: string;
}

/** Deterministic, zero-LLM-cost suggestions computed from graph holes. */
function SuggestionHints({
  projectId,
  entities,
  onPick,
}: {
  projectId: string;
  entities: Entity[];
  onPick: (hint: Hint) => void;
}) {
  const { t } = useTranslation();
  const { data: edges } = useQuery({
    queryKey: ["edges", projectId],
    queryFn: () => apiClient.get<Edge[]>(`/api/projects/${projectId}/edges`),
  });

  const hints = useMemo<Hint[]>(() => {
    if (!edges || entities.length === 0) return [];
    const connected = new Set<string>();
    for (const edge of edges) {
      connected.add(edge.source_entity_id);
      connected.add(edge.target_entity_id);
    }
    return entities
      .filter((entity) => !connected.has(entity.id))
      .slice(0, 2)
      .map((entity) => ({
        text: t("assistant.hintIsolatedText", { title: entity.title }),
        instruction: t("assistant.hintIsolatedInstruction", { title: entity.title }),
        anchorId: entity.id,
      }));
  }, [edges, entities, t]);

  if (hints.length === 0) return null;
  return (
    <div className="assistant-hints">
      {hints.map((hint) => (
        <button
          key={hint.anchorId ?? hint.text}
          type="button"
          className="assistant-hint-chip"
          onClick={() => onPick(hint)}
        >
          {hint.text}
        </button>
      ))}
    </div>
  );
}

function ReviewCard({
  review,
  entities,
  busy,
  onDecision,
}: {
  review: AgentReviewPayload;
  entities: Entity[];
  busy: boolean;
  onDecision: (
    action: "approve" | "reject" | "revise",
    draft: LoreDraft,
    feedback?: string,
  ) => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<LoreDraft>(review.draft!);
  const [removedRefs, setRemovedRefs] = useState<Set<string>>(new Set());
  const [removedRelationships, setRemovedRelationships] = useState<Set<number>>(
    new Set(),
  );
  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);

  // A revise replaces the payload — resync local editing state.
  useEffect(() => {
    setDraft(review.draft!);
    setRemovedRefs(new Set());
    setRemovedRelationships(new Set());
    setFeedback("");
    setShowFeedback(false);
  }, [review]);

  const existingTitleById = useMemo(
    () => new Map(entities.map((entity) => [entity.id, entity.title])),
    [entities],
  );
  const draftTitleByRef = useMemo(
    () => new Map(draft.entities.map((entity) => [entity.ref, entity.title])),
    [draft.entities],
  );

  const targetName = (ref: string) =>
    draftTitleByRef.get(ref) ?? existingTitleById.get(ref) ?? ref;

  function keptDraft(): LoreDraft {
    const keptEntities = draft.entities.filter((e) => !removedRefs.has(e.ref));
    const keptRefs = new Set(keptEntities.map((e) => e.ref));
    return {
      entities: keptEntities,
      relationships: draft.relationships.filter(
        (relationship, index) =>
          !removedRelationships.has(index) &&
          keptRefs.has(relationship.source_ref) &&
          (keptRefs.has(relationship.target_ref) ||
            existingTitleById.has(relationship.target_ref)),
      ),
    };
  }

  function updateEntity(ref: string, patch: Partial<DraftEntity>) {
    setDraft((prev) => ({
      ...prev,
      entities: prev.entities.map((entity) =>
        entity.ref === ref ? { ...entity, ...patch } : entity,
      ),
    }));
  }

  const keptCount = draft.entities.length - removedRefs.size;

  return (
    <div className="assistant-review">
      {review.warnings.length > 0 && (
        <ul className="assistant-warnings">
          {review.warnings.map((warning, index) => (
            <li key={`${warning.code}-${index}`}>⚠ {translateWarning(warning, t)}</li>
          ))}
        </ul>
      )}

      <div className="assistant-draft-entities">
        {draft.entities.map((entity) => {
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
                {entity.grounded_in.length === 0 && (
                  <span
                    className="assistant-draft-new"
                    title={t("assistant.review.newBadgeTitle")}
                  >
                    ✨
                  </span>
                )}
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

      {draft.relationships.length > 0 && (
        <div className="assistant-relationships">
          {draft.relationships.map((relationship, index) => {
            const blocked =
              removedRefs.has(relationship.source_ref) ||
              (removedRefs.has(relationship.target_ref) &&
                !existingTitleById.has(relationship.target_ref));
            const removed = removedRelationships.has(index) || blocked;
            return (
              <label
                key={`${relationship.source_ref}-${relationship.type}-${relationship.target_ref}`}
                className={
                  removed ? "assistant-relationship removed" : "assistant-relationship"
                }
              >
                <input
                  type="checkbox"
                  checked={!removed}
                  disabled={blocked}
                  onChange={() =>
                    setRemovedRelationships((prev) => {
                      const next = new Set(prev);
                      if (next.has(index)) next.delete(index);
                      else next.add(index);
                      return next;
                    })
                  }
                />
                <span>
                  <strong>{targetName(relationship.source_ref)}</strong> —
                  {relationship.type}→{" "}
                  <strong>{targetName(relationship.target_ref)}</strong>
                  <em> {relationship.reason}</em>
                </span>
              </label>
            );
          })}
        </div>
      )}

      <p className="assistant-review-cost">
        {t("assistant.review.tokensSuffix", {
          count: review.input_tokens + review.output_tokens,
        })}
      </p>

      {showFeedback && (
        <div className="assistant-feedback">
          <textarea
            rows={2}
            autoFocus
            placeholder={t("assistant.review.feedbackPlaceholder")}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
          <button
            type="button"
            disabled={!feedback.trim() || busy}
            onClick={() => onDecision("revise", keptDraft(), feedback.trim())}
          >
            {t("assistant.review.sendRevision")}
          </button>
        </div>
      )}

      <div className="assistant-review-actions">
        <button
          type="button"
          className="assistant-approve"
          disabled={busy || keptCount === 0}
          onClick={() => onDecision("approve", keptDraft())}
        >
          {t("assistant.review.approve", { count: keptCount })}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => setShowFeedback((v) => !v)}
        >
          {t("assistant.review.requestChanges")}
        </button>
        <button
          type="button"
          className="assistant-reject"
          disabled={busy}
          onClick={() => onDecision("reject", draft)}
        >
          {t("assistant.review.reject")}
        </button>
      </div>
    </div>
  );
}
