import { describe, expect, it } from "vitest";

import { clampTextareaHeight } from "./useAutoGrowTextarea";

const limits = { minHeightPx: 52, maxHeightPx: 200 };

describe("clampTextareaHeight", () => {
  it("floors short content at the minimum height", () => {
    expect(clampTextareaHeight(0, limits)).toBe(52);
    expect(clampTextareaHeight(30, limits)).toBe(52);
  });

  it("passes through content within bounds unchanged", () => {
    expect(clampTextareaHeight(120, limits)).toBe(120);
  });

  it("caps tall content at the maximum height", () => {
    expect(clampTextareaHeight(500, limits)).toBe(200);
  });

  it("treats the bounds as inclusive", () => {
    expect(clampTextareaHeight(52, limits)).toBe(52);
    expect(clampTextareaHeight(200, limits)).toBe(200);
  });
});
