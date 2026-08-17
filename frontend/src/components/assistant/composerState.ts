/** Enter sends, Shift+Enter inserts a newline — the universal chat-input
 * convention. */
export function isSubmitKeypress(key: string, shiftKey: boolean): boolean {
  return key === "Enter" && !shiftKey;
}

export interface ComposerAvailability {
  /** Input and attach/context controls are disabled — busy or awaiting a
   * review decision. */
  blocked: boolean;
  /** Whether the Send button itself may be pressed right now. */
  canSend: boolean;
}

/** A draft review in progress blocks new messages until the DM resolves it
 * (approve/reject/revise) — the backend enforces this too; mirroring it here
 * just keeps the composer from offering a send that would be rejected. */
export function composerAvailability(params: {
  text: string;
  busy: boolean;
  reviewPending: boolean;
}): ComposerAvailability {
  const blocked = params.busy || params.reviewPending;
  return { blocked, canSend: !blocked && params.text.trim().length > 0 };
}
