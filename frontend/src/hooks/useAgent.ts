import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  type AgentChatMessage,
  type AgentEvent,
  type AgentResumeRequest,
  type AgentReviewPayload,
  agentApi,
  fileToChatAttachment,
} from "../api/agent";
import { translateApiError } from "../i18n/eventText";

export function useAgentConfig() {
  return useQuery({ queryKey: ["agent-config"], queryFn: agentApi.config });
}

export function useAgentSessions(projectId: string) {
  return useQuery({
    queryKey: ["agent-sessions", projectId],
    queryFn: () => agentApi.list(projectId),
  });
}

interface StreamedMessage extends AgentChatMessage {
  /** true while tokens are still arriving for this bubble */
  streaming?: boolean;
}

export interface AgentChat {
  threadId: string | null;
  messages: StreamedMessage[];
  /** current pipeline node while a turn runs, null when idle */
  statusNode: string | null;
  pendingReview: AgentReviewPayload | null;
  busy: boolean;
  error: string | null;
  send: (
    text: string,
    anchorEntityId?: string | null,
    attachments?: File[],
  ) => Promise<void>;
  review: (decision: AgentResumeRequest) => Promise<void>;
  openSession: (threadId: string) => Promise<void>;
  reset: () => void;
}

/** One conversation with the assistant: local transcript with streaming
 * tokens/status, the pending review payload, and turn actions. */
export function useAgentChat(
  projectId: string,
  onCommitted?: (entityIds: string[]) => void,
): AgentChat {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<StreamedMessage[]>([]);
  const [statusNode, setStatusNode] = useState<string | null>(null);
  const [pendingReview, setPendingReview] = useState<AgentReviewPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Async closures (send/review) need the freshest threadId, not the one
  // captured at render time.
  const threadIdRef = useRef<string | null>(null);

  const handleEvent = useCallback(
    (event: AgentEvent) => {
      switch (event.type) {
        case "status":
          setStatusNode(event.node);
          break;
        case "token":
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant" && last.streaming) {
              return [
                ...prev.slice(0, -1),
                { ...last, text: last.text + event.text },
              ];
            }
            return [
              ...prev,
              {
                role: "assistant",
                text: event.text,
                attachments: [],
                streaming: true,
              },
            ];
          });
          break;
        case "review":
          setPendingReview(event.payload);
          break;
        case "error":
          setError(
            event.code
              ? t(`errors.${event.code}`, { defaultValue: event.detail })
              : event.detail,
          );
          break;
        case "done": {
          const session = event.session;
          if (session.status !== "awaiting_review") setPendingReview(null);
          if (session.status === "committed") {
            onCommitted?.(session.committed_entity_ids);
            void queryClient.invalidateQueries({ queryKey: ["entities", projectId] });
            void queryClient.invalidateQueries({ queryKey: ["edges", projectId] });
          }
          void queryClient.invalidateQueries({
            queryKey: ["agent-sessions", projectId],
          });
          break;
        }
      }
    },
    [onCommitted, projectId, queryClient, t],
  );

  const runTurn = useCallback(
    async (turn: () => Promise<void>) => {
      setBusy(true);
      setError(null);
      try {
        await turn();
        // Replace streamed partials with the authoritative transcript
        // (includes deterministic acks the token stream never carries).
        if (threadIdRef.current) {
          const detail = await agentApi.detail(projectId, threadIdRef.current);
          setMessages(detail.messages);
        }
      } catch (err) {
        setError(translateApiError(err, t));
      } finally {
        setStatusNode(null);
        setBusy(false);
      }
    },
    [projectId, t],
  );

  const send = useCallback(
    async (
      text: string,
      anchorEntityId: string | null = null,
      files: File[] = [],
    ) => {
      let tid = threadIdRef.current;
      if (!tid) {
        const session = await agentApi.createSession(projectId);
        tid = session.thread_id;
        setThreadId(tid);
        threadIdRef.current = tid;
      }
      setMessages((prev) => [
        ...prev,
        { role: "user", text, attachments: files.map((f) => f.name) },
      ]);
      const attachments = await Promise.all(files.map(fileToChatAttachment));
      await runTurn(() =>
        agentApi.streamMessage(
          projectId,
          tid,
          text,
          anchorEntityId,
          attachments,
          handleEvent,
        ),
      );
    },
    [projectId, runTurn, handleEvent],
  );

  const review = useCallback(
    async (decision: AgentResumeRequest) => {
      const tid = threadIdRef.current;
      if (!tid) return;
      if (decision.action !== "revise") setPendingReview(null);
      await runTurn(() =>
        agentApi.streamReview(projectId, tid, decision, handleEvent),
      );
    },
    [projectId, runTurn, handleEvent],
  );

  const openSession = useCallback(
    async (tid: string) => {
      const detail = await agentApi.detail(projectId, tid);
      setThreadId(tid);
      threadIdRef.current = tid;
      setMessages(detail.messages);
      setPendingReview(detail.status === "awaiting_review" ? detail.review : null);
      setError(null);
    },
    [projectId],
  );

  const reset = useCallback(() => {
    setThreadId(null);
    threadIdRef.current = null;
    setMessages([]);
    setPendingReview(null);
    setError(null);
  }, []);

  return {
    threadId,
    messages,
    statusNode,
    pendingReview,
    busy,
    error,
    send,
    review,
    openSession,
    reset,
  };
}
