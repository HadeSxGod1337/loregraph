import { describe, expect, it } from "vitest";

import { moveMenuIndex, sessionStatusTone } from "./sessionMenu";

describe("sessionStatusTone", () => {
  it("maps each status to its tone", () => {
    expect(sessionStatusTone("idle")).toBe("neutral");
    expect(sessionStatusTone("running")).toBe("neutral");
    expect(sessionStatusTone("awaiting_review")).toBe("accent");
    expect(sessionStatusTone("committed")).toBe("success");
    expect(sessionStatusTone("rejected")).toBe("danger");
    expect(sessionStatusTone("failed")).toBe("danger");
  });
});

describe("moveMenuIndex", () => {
  it("starts at the first item on ArrowDown from no selection", () => {
    expect(moveMenuIndex(-1, "ArrowDown", 3)).toBe(0);
  });

  it("starts at the last item on ArrowUp from no selection", () => {
    expect(moveMenuIndex(-1, "ArrowUp", 3)).toBe(2);
  });

  it("wraps from the last item to the first on ArrowDown", () => {
    expect(moveMenuIndex(2, "ArrowDown", 3)).toBe(0);
  });

  it("wraps from the first item to the last on ArrowUp", () => {
    expect(moveMenuIndex(0, "ArrowUp", 3)).toBe(2);
  });

  it("steps forward and backward within bounds", () => {
    expect(moveMenuIndex(0, "ArrowDown", 3)).toBe(1);
    expect(moveMenuIndex(1, "ArrowUp", 3)).toBe(0);
  });

  it("Home and End jump to the ends regardless of current position", () => {
    expect(moveMenuIndex(1, "Home", 5)).toBe(0);
    expect(moveMenuIndex(1, "End", 5)).toBe(4);
  });

  it("returns -1 for an empty list", () => {
    expect(moveMenuIndex(-1, "ArrowDown", 0)).toBe(-1);
  });
});
