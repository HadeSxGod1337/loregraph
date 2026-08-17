import { describe, expect, it } from "vitest";

import { eventTone } from "./eventText";

describe("eventTone", () => {
  it("marks commit/update acks as success", () => {
    expect(eventTone("batch_committed")).toBe("success");
    expect(eventTone("entity_updated")).toBe("success");
    expect(eventTone("relationships_committed")).toBe("success");
    expect(eventTone("changes_committed")).toBe("success");
  });

  it("marks rejections and failures as danger", () => {
    expect(eventTone("batch_rejected")).toBe("danger");
    expect(eventTone("draft_failed")).toBe("danger");
    expect(eventTone("edit_failed")).toBe("danger");
    expect(eventTone("relationships_failed")).toBe("danger");
  });

  it("marks budget/staleness notices as warning", () => {
    expect(eventTone("review_stale")).toBe("warning");
    expect(eventTone("budget_exhausted_reply")).toBe("warning");
  });

  it("falls back to neutral for anything unrecognized", () => {
    expect(eventTone("brainstorm_empty")).toBe("neutral");
    expect(eventTone("some_future_event_code")).toBe("neutral");
  });
});
