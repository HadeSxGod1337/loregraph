import { useEffect, useRef } from "react";

import { type ProjectEvent, wsUrl } from "../api/realtime";

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 10_000;
// Grace period before actually closing the socket after the last listener
// unsubscribes — avoids reconnect thrash when e.g. a page briefly remounts
// (route change) while another component on the same project is about to
// subscribe again.
const CLOSE_GRACE_MS = 2000;

type Listener = (event: ProjectEvent) => void;

/** One shared WebSocket per project, ref-counted across every
 * useProjectEvent() call for that project — components don't each open
 * their own socket. Auto-reconnects with backoff, replaying only what was
 * missed (`catch_up_from`) via the server's per-project ring buffer (see
 * backend services/event_bus.py). */
class ProjectEventChannel {
  private socket: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private lastSeq: number | undefined;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closeTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUs = false;
  private readonly projectId: string;

  constructor(projectId: string) {
    this.projectId = projectId;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    if (this.closeTimer) {
      clearTimeout(this.closeTimer);
      this.closeTimer = null;
    }
    this.ensureConnected();
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) {
        this.closeTimer = setTimeout(() => this.close(), CLOSE_GRACE_MS);
      }
    };
  }

  private ensureConnected(): void {
    if (this.socket) return;
    this.closedByUs = false;
    const socket = new WebSocket(wsUrl(this.projectId, this.lastSeq));
    this.socket = socket;
    socket.onmessage = (message: MessageEvent<string>) => {
      let event: ProjectEvent;
      try {
        event = JSON.parse(message.data) as ProjectEvent;
      } catch {
        return;
      }
      this.lastSeq = event.seq;
      for (const listener of this.listeners) listener(event);
    };
    socket.onopen = () => {
      this.reconnectAttempt = 0;
    };
    socket.onclose = () => {
      this.socket = null;
      if (this.closedByUs || this.listeners.size === 0) return;
      const delay = Math.min(
        RECONNECT_BASE_DELAY_MS * 2 ** this.reconnectAttempt,
        RECONNECT_MAX_DELAY_MS,
      );
      this.reconnectAttempt += 1;
      this.reconnectTimer = setTimeout(() => this.ensureConnected(), delay);
    };
  }

  private close(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.closedByUs = true;
    this.socket?.close();
    this.socket = null;
    channels.delete(this.projectId);
  }
}

const channels = new Map<string, ProjectEventChannel>();

function getChannel(projectId: string): ProjectEventChannel {
  let channel = channels.get(projectId);
  if (!channel) {
    channel = new ProjectEventChannel(projectId);
    channels.set(projectId, channel);
  }
  return channel;
}

/** Subscribes `handler` to every realtime event of `type` for `projectId`.
 * Pass a falsy projectId to skip connecting (e.g. before a project is
 * chosen) — the same pattern as react-query's `enabled` option. */
export function useProjectEvent<TPayload = Record<string, unknown>>(
  projectId: string | null | undefined,
  type: string,
  handler: (payload: TPayload, event: ProjectEvent<TPayload>) => void,
): void {
  // Always the latest handler, without re-subscribing on every render (the
  // effect below only depends on projectId/type).
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (!projectId) return;
    const channel = getChannel(projectId);
    return channel.subscribe((event) => {
      if (event.type === type) {
        handlerRef.current(event.payload as TPayload, event as ProjectEvent<TPayload>);
      }
    });
  }, [projectId, type]);
}
