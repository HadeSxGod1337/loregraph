import { describe, expect, it } from "vitest";

import { deriveEmbedStatus } from "./useEmbedLoadStatus";

describe("deriveEmbedStatus", () => {
  it("is loading until the frame settles or times out", () => {
    expect(deriveEmbedStatus(false, false, false)).toBe("loading");
  });

  it("treats a load that fires before the minimum window as blocked", () => {
    expect(deriveEmbedStatus(true, false, false)).toBe("blocked");
  });

  it("treats a load that fires after the minimum window as embedded", () => {
    expect(deriveEmbedStatus(true, true, false)).toBe("embedded");
  });

  it("treats a hard timeout with no load as blocked", () => {
    expect(deriveEmbedStatus(false, true, true)).toBe("blocked");
  });

  it("prefers a late load over a timeout that fired first", () => {
    expect(deriveEmbedStatus(true, true, true)).toBe("embedded");
  });
});
