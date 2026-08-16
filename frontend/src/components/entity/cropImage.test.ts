import { describe, expect, it } from "vitest";

import { computeCoverLayout, computeFitLayout } from "./cropImage";

describe("computeFitLayout", () => {
  it("draws edge-to-edge with no padding when the source already matches the aspect", () => {
    const layout = computeFitLayout(400, 200, 2);
    expect(layout).toEqual({
      canvasWidth: 400,
      canvasHeight: 200,
      drawWidth: 400,
      drawHeight: 200,
      dx: 0,
      dy: 0,
    });
  });

  it("pads a square source left/right to reach a wider aspect", () => {
    const layout = computeFitLayout(200, 200, 2);
    expect(layout).toEqual({
      canvasWidth: 400,
      canvasHeight: 200,
      drawWidth: 200,
      drawHeight: 200,
      dx: 100,
      dy: 0,
    });
  });

  it("pads a tall source left/right, never cropping it", () => {
    const layout = computeFitLayout(100, 400, 2);
    expect(layout).toEqual({
      canvasWidth: 800,
      canvasHeight: 400,
      drawWidth: 100,
      drawHeight: 400,
      dx: 350,
      dy: 0,
    });
  });

  it("scales the whole box down together once the long edge exceeds the cap", () => {
    const layout = computeFitLayout(2000, 1000, 2, 500);
    expect(layout).toEqual({
      canvasWidth: 500,
      canvasHeight: 250,
      drawWidth: 500,
      drawHeight: 250,
      dx: 0,
      dy: 0,
    });
  });

  it("caps and pads at once without losing any of the source", () => {
    const layout = computeFitLayout(200, 200, 2, 200);
    expect(layout).toEqual({
      canvasWidth: 200,
      canvasHeight: 100,
      drawWidth: 100,
      drawHeight: 100,
      dx: 50,
      dy: 0,
    });
  });

  it("never upscales a source under the cap", () => {
    const layout = computeFitLayout(64, 64, 2);
    expect(layout.drawWidth).toBe(64);
    expect(layout.drawHeight).toBe(64);
  });
});

describe("computeCoverLayout", () => {
  it("draws edge-to-edge with no overhang when the source already matches the target", () => {
    const layout = computeCoverLayout(400, 200, 400, 200);
    expect(layout).toEqual({ drawWidth: 400, drawHeight: 200, dx: 0, dy: 0 });
  });

  it("overhangs left/right for a source wider than the target box", () => {
    // 4:1 source into a 2:1 box — height matches exactly, width spills over.
    const layout = computeCoverLayout(800, 200, 400, 200);
    expect(layout).toEqual({ drawWidth: 800, drawHeight: 200, dx: -200, dy: 0 });
  });

  it("overhangs top/bottom for a source taller (portrait) than the target box", () => {
    // A portrait source into a 2:1 wide box — width matches exactly, height spills over.
    const layout = computeCoverLayout(200, 800, 400, 200);
    expect(layout).toEqual({ drawWidth: 400, drawHeight: 1600, dx: 0, dy: -700 });
  });

  it("scales a square source down to cover a smaller square target", () => {
    const layout = computeCoverLayout(300, 300, 150, 150);
    expect(layout).toEqual({ drawWidth: 150, drawHeight: 150, dx: 0, dy: 0 });
  });

  it("never distorts the source's own aspect ratio", () => {
    // Chosen so the covering scale (0.44) divides both dimensions to a
    // whole pixel — an arbitrary ratio would drift slightly under the
    // independent Math.round on width and height, same as computeFitLayout.
    const layout = computeCoverLayout(500, 300, 220, 88);
    expect(layout.drawWidth / layout.drawHeight).toBeCloseTo(500 / 300, 5);
  });

  it("overscan inflates the draw size symmetrically past a plain cover", () => {
    const plain = computeCoverLayout(400, 200, 400, 200);
    const overscanned = computeCoverLayout(400, 200, 400, 200, 1.15);
    expect(overscanned).toEqual({ drawWidth: 460, drawHeight: 230, dx: -30, dy: -15 });
    // The overscanned box still fully contains the plain-cover box.
    expect(overscanned.drawWidth).toBeGreaterThan(plain.drawWidth);
    expect(overscanned.dx).toBeLessThan(plain.dx);
  });
});
