import { describe, expect, it } from "vitest";

import { computeFitLayout } from "./cropImage";

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
