import { describe, expect, it } from "vitest";

import { computeEdgeEmphasis, edgeGroupOffsets, getOffsetPath } from "./floatingEdgeUtils";

describe("edgeGroupOffsets", () => {
  it("returns a single centered offset for a lone edge", () => {
    expect(edgeGroupOffsets(1)).toEqual([0]);
  });

  it("spreads offsets symmetrically around zero", () => {
    expect(edgeGroupOffsets(2)).toEqual([-23, 23]);
    expect(edgeGroupOffsets(3)).toEqual([-46, 0, 46]);
  });
});

describe("getOffsetPath", () => {
  it("keeps a lone edge (offset 0) a straight line centered between the endpoints", () => {
    const [, labelX, labelY] = getOffsetPath(0, 0, 100, 0, 0);
    expect(labelX).toBe(50);
    expect(labelY).toBe(0);
  });

  it("bows a bidirectional pair to opposite sides instead of coinciding", () => {
    // Same node pair, opposite direction, the offsets edgeGroupOffsets(2)
    // actually hands out — without the source/target canonicalization in
    // getOffsetPath, the direction flip cancels the offset-sign flip and
    // both edges land on the same control point (see its own comment).
    const [forwardOffset, reverseOffset] = edgeGroupOffsets(2);
    const [, , labelYForward] = getOffsetPath(0, 0, 100, 0, forwardOffset);
    const [, , labelYReverse] = getOffsetPath(100, 0, 0, 0, reverseOffset);
    expect(labelYForward).not.toBeCloseTo(labelYReverse);
    expect(Math.sign(labelYForward)).not.toBe(Math.sign(labelYReverse));
  });
});

describe("computeEdgeEmphasis", () => {
  const base = {
    sourceId: "a",
    targetId: "b",
    hoveredEntityId: null,
    selectedEntityId: null,
    rootId: "",
  };

  it("is neither emphasized nor dimmed with no focal entity", () => {
    expect(computeEdgeEmphasis(base)).toEqual({ emphasized: false, dimmed: false });
  });

  it("emphasizes edges incident to the hovered entity and dims unrelated ones", () => {
    expect(computeEdgeEmphasis({ ...base, hoveredEntityId: "a" })).toEqual({
      emphasized: true,
      dimmed: false,
    });
    expect(computeEdgeEmphasis({ ...base, hoveredEntityId: "c" })).toEqual({
      emphasized: false,
      dimmed: true,
    });
  });

  it("emphasizes edges incident to the selected entity without dimming others", () => {
    expect(computeEdgeEmphasis({ ...base, selectedEntityId: "b" })).toEqual({
      emphasized: true,
      dimmed: false,
    });
    expect(computeEdgeEmphasis({ ...base, selectedEntityId: "c" })).toEqual({
      emphasized: false,
      dimmed: false,
    });
  });

  it("emphasizes edges incident to the root entity without dimming others", () => {
    expect(computeEdgeEmphasis({ ...base, rootId: "a" })).toEqual({
      emphasized: true,
      dimmed: false,
    });
    expect(computeEdgeEmphasis({ ...base, rootId: "c" })).toEqual({
      emphasized: false,
      dimmed: false,
    });
  });

  it("never dims an edge that selection/root already emphasize, even while an unrelated node is hovered", () => {
    expect(
      computeEdgeEmphasis({
        sourceId: "a",
        targetId: "b",
        hoveredEntityId: "c",
        selectedEntityId: "b",
        rootId: "",
      }),
    ).toEqual({ emphasized: true, dimmed: false });
  });
});
