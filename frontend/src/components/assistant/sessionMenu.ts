import type { AgentSessionStatus } from "../../api/agent";

export type SessionStatusTone = "neutral" | "accent" | "success" | "danger";

const SESSION_STATUS_TONE: Record<AgentSessionStatus, SessionStatusTone> = {
  idle: "neutral",
  running: "neutral",
  awaiting_review: "accent",
  committed: "success",
  rejected: "danger",
  failed: "danger",
};

/** Coarse visual category for a session status badge in the history menu. */
export function sessionStatusTone(status: AgentSessionStatus): SessionStatusTone {
  return SESSION_STATUS_TONE[status];
}

/** Roving focus for the history menu's Arrow/Home/End handling — kept as a
 * pure index calculation so wrap-around at the ends is unit-testable
 * without a DOM. `current` of -1 (nothing focused yet) starts at the first
 * or last item depending on direction. */
export function moveMenuIndex(
  current: number,
  key: "ArrowDown" | "ArrowUp" | "Home" | "End",
  length: number,
): number {
  if (length === 0) return -1;
  switch (key) {
    case "ArrowDown":
      return current < 0 ? 0 : (current + 1) % length;
    case "ArrowUp":
      return current <= 0 ? length - 1 : current - 1;
    case "Home":
      return 0;
    case "End":
      return length - 1;
  }
}
