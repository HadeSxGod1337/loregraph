import { describe, expect, it } from "vitest";

import { deriveEmbedStatus } from "./useEmbedLoadStatus";

describe("deriveEmbedStatus", () => {
  it("is loading until the frame loads or times out", () => {
    expect(deriveEmbedStatus(false, false)).toBe("loading");
  });

  it("trusts a load event whenever it fires", () => {
    expect(deriveEmbedStatus(true, false)).toBe("embedded");
  });

  it("falls back once maxWaitMs passes with no load at all", () => {
    expect(deriveEmbedStatus(false, true)).toBe("blocked");
  });

  it("prefers a load that arrives right as the timeout fires", () => {
    expect(deriveEmbedStatus(true, true)).toBe("embedded");
  });
});
