import { apiClient, streamSse } from "./client";

// Mirrors backend schemas/agent.py — one contract, used verbatim.

export interface DraftField {
  key: string;
  value: string;
}

export interface DraftEntity {
  ref: string;
  type: string;
  title: string;
  summary: string;
  fields: DraftField[];
  grounded_in: string[];
}

export type RelationshipOp = "create" | "update" | "delete";

export interface DraftRelationship {
  /** Absent on drafts persisted before ops existed — treat as "create". */
  op?: RelationshipOp;
  /** create: a draft ref or an existing entity id, on either side. */
  source_ref: string;
  target_ref: string;
  /** update/delete: the existing relationship being acted on. */
  edge_id?: string | null;
  type: string;
  reason: string;
  /** update: flip the relationship's direction. */
  reverse?: boolean;
  grounded_in: string[];
}

export interface LoreDraft {
  entities: DraftEntity[];
  relationships: DraftRelationship[];
}

export interface EntityEditDraft {
  entity_id: string;
  type: string;
  title: string;
  summary: string;
  fields: DraftField[];
  edit_reason: string;
}

/** Mirrors backend schemas/agent.py AgentWarning — a structured,
 * machine-translatable warning. `code === "llm_text"` is the one exception:
 * free text from an LLM judge, already in the conversation's language,
 * carried in `params.text` and rendered as-is (see i18n/eventText.ts). */
export interface AgentWarning {
  code: string;
  params: Record<string, string>;
}

export interface AgentReviewPayload {
  draft: LoreDraft | null;
  entity_edit_draft: EntityEditDraft | null;
  warnings: AgentWarning[];
  input_tokens: number;
  output_tokens: number;
}

export type AgentSessionStatus =
  | "idle"
  | "running"
  | "awaiting_review"
  | "committed"
  | "rejected"
  | "failed";

export interface AgentSession {
  thread_id: string;
  project_id: string;
  status: AgentSessionStatus;
  title: string;
  input_tokens: number;
  output_tokens: number;
  committed_entity_ids: string[];
  review: AgentReviewPayload | null;
  created_at: string;
  updated_at: string;
}

export interface AgentChatMessage {
  role: "user" | "assistant";
  text: string;
  attachments: string[];
  // Set only for deterministic, backend-composed messages (commit acks,
  // budget notices) — see i18n/eventText.ts for how these render.
  event_code?: string | null;
  event_params?: Record<string, string>;
}

/** One file attached to a single chat turn — NOT the project's knowledge
 * base (see components/knowledge/KnowledgeBasePanel.tsx). Lives only inside
 * that turn's message; never becomes a persistent, searchable document. */
export interface ChatAttachment {
  filename: string;
  content_type: string;
  data_base64: string;
}

export interface AgentSessionDetail extends AgentSession {
  messages: AgentChatMessage[];
}

export interface AgentResumeRequest {
  action: "approve" | "reject" | "revise";
  draft?: LoreDraft | null;
  feedback?: string | null;
}

export interface AgentConfig {
  llm_configured: boolean;
  llm_provider: string;
  vector_enabled: boolean;
}

export type AgentEvent =
  | { type: "status"; node: string }
  | { type: "token"; text: string }
  | { type: "review"; payload: AgentReviewPayload }
  | { type: "done"; session: AgentSession }
  | { type: "error"; code?: string; detail: string };

/** POST an SSE endpoint and feed parsed events to the callback. Thin,
 * agent-typed wrapper over the shared streamSse (see api/client.ts). */
export async function streamAgentTurn(
  path: string,
  body: unknown,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  await streamSse<AgentEvent>(path, body, onEvent);
}

/** Encodes a browser File into the base64 payload the backend expects for
 * chat attachments (see agent/multimodal.py). */
export async function fileToChatAttachment(file: File): Promise<ChatAttachment> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error as DOMException);
    reader.readAsDataURL(file);
  });
  return {
    filename: file.name,
    content_type: file.type || "application/octet-stream",
    data_base64: dataUrl.slice(dataUrl.indexOf(",") + 1),
  };
}

export const agentApi = {
  config: () => apiClient.get<AgentConfig>("/api/agent/config"),
  createSession: (projectId: string) =>
    apiClient.post<AgentSession>(`/api/projects/${projectId}/agent/sessions`),
  list: (projectId: string) =>
    apiClient.get<AgentSession[]>(`/api/projects/${projectId}/agent/sessions`),
  detail: (projectId: string, threadId: string) =>
    apiClient.get<AgentSessionDetail>(
      `/api/projects/${projectId}/agent/sessions/${threadId}`,
    ),
  streamMessage: (
    projectId: string,
    threadId: string,
    text: string,
    anchorEntityId: string | null,
    attachments: ChatAttachment[],
    onEvent: (event: AgentEvent) => void,
  ) =>
    streamAgentTurn(
      `/api/projects/${projectId}/agent/sessions/${threadId}/messages`,
      { text, anchor_entity_id: anchorEntityId, attachments },
      onEvent,
    ),
  streamReview: (
    projectId: string,
    threadId: string,
    decision: AgentResumeRequest,
    onEvent: (event: AgentEvent) => void,
  ) =>
    streamAgentTurn(
      `/api/projects/${projectId}/agent/sessions/${threadId}/review`,
      decision,
      onEvent,
    ),
  /** Second entry point for a skill (see backend agent/skills/registry.py):
   * runs it directly on a fresh/idle session, with no assistant LLM call
   * deciding whether to fire — for UI-driven triggers (a button) that must
   * work deterministically regardless of model judgment. Same SSE shape as
   * streamMessage/streamReview. */
  streamSkillRun: (
    projectId: string,
    threadId: string,
    skillName: string,
    input: Record<string, unknown>,
    onEvent: (event: AgentEvent) => void,
  ) =>
    streamAgentTurn(
      `/api/projects/${projectId}/agent/sessions/${threadId}/skills/${skillName}/run`,
      { input },
      onEvent,
    ),
};
