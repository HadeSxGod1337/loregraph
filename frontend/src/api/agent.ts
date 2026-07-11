import { API_URL, ApiError, apiClient } from "./client";

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

export interface DraftRelationship {
  source_ref: string;
  target_ref: string;
  type: string;
  reason: string;
  grounded_in: string[];
}

export interface LoreDraft {
  entities: DraftEntity[];
  relationships: DraftRelationship[];
}

export interface AgentReviewPayload {
  draft: LoreDraft | null;
  warnings: string[];
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
  | { type: "error"; detail: string };

/** POST an SSE endpoint and feed parsed events to the callback. EventSource
 * can't POST, so this reads the fetch body stream directly. */
export async function streamAgentTurn(
  path: string,
  body: unknown,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const response = await fetch(API_URL + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    let detail = response.statusText;
    try {
      const errorBody = (await response.json()) as { detail?: string };
      detail = errorBody.detail ?? detail;
    } catch {
      // no JSON body
    }
    throw new ApiError(
      response.status,
      `${detail} (POST ${path} → HTTP ${response.status})`,
    );
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (raw.startsWith("data: ")) {
        onEvent(JSON.parse(raw.slice(6)) as AgentEvent);
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
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
    onEvent: (event: AgentEvent) => void,
  ) =>
    streamAgentTurn(
      `/api/projects/${projectId}/agent/sessions/${threadId}/messages`,
      { text, anchor_entity_id: anchorEntityId },
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
};
