import { describe, expect, it } from "vitest";

import { composerAvailability, isSubmitKeypress } from "./composerState";

describe("isSubmitKeypress", () => {
  it("submits on plain Enter", () => {
    expect(isSubmitKeypress("Enter", false)).toBe(true);
  });

  it("does not submit on Shift+Enter", () => {
    expect(isSubmitKeypress("Enter", true)).toBe(false);
  });

  it("ignores other keys", () => {
    expect(isSubmitKeypress("a", false)).toBe(false);
    expect(isSubmitKeypress("Tab", false)).toBe(false);
  });
});

describe("composerAvailability", () => {
  it("allows sending non-blank text when idle", () => {
    expect(composerAvailability({ text: "hello", busy: false, reviewPending: false })).toEqual({
      blocked: false,
      canSend: true,
    });
  });

  it("blocks sending while busy", () => {
    const result = composerAvailability({ text: "hello", busy: true, reviewPending: false });
    expect(result.blocked).toBe(true);
    expect(result.canSend).toBe(false);
  });

  it("blocks sending while a review is pending", () => {
    const result = composerAvailability({ text: "hello", busy: false, reviewPending: true });
    expect(result.blocked).toBe(true);
    expect(result.canSend).toBe(false);
  });

  it("disables send for blank or whitespace-only text", () => {
    expect(composerAvailability({ text: "", busy: false, reviewPending: false }).canSend).toBe(
      false,
    );
    expect(composerAvailability({ text: "   ", busy: false, reviewPending: false }).canSend).toBe(
      false,
    );
  });
});
