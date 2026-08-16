import { describe, expect, it } from "vitest";

import { LOD_ENTER_ZOOM, LOD_EXIT_ZOOM, nextLodState } from "./lod";

describe("nextLodState", () => {
  it("enters LOD once zoom drops below the enter threshold", () => {
    expect(nextLodState(false, LOD_ENTER_ZOOM + 0.01)).toBe(false);
    expect(nextLodState(false, LOD_ENTER_ZOOM - 0.01)).toBe(true);
  });

  it("exits LOD once zoom rises above the exit threshold", () => {
    expect(nextLodState(true, LOD_EXIT_ZOOM - 0.01)).toBe(true);
    expect(nextLodState(true, LOD_EXIT_ZOOM + 0.01)).toBe(false);
  });

  it("holds state inside the dead zone regardless of direction", () => {
    const midpoint = (LOD_ENTER_ZOOM + LOD_EXIT_ZOOM) / 2;
    expect(nextLodState(false, midpoint)).toBe(false);
    expect(nextLodState(true, midpoint)).toBe(true);
  });

  it("does not flip-flop from repeated calls exactly at one boundary", () => {
    let isLod = false;
    for (let i = 0; i < 5; i++) isLod = nextLodState(isLod, LOD_ENTER_ZOOM);
    expect(isLod).toBe(false);

    isLod = true;
    for (let i = 0; i < 5; i++) isLod = nextLodState(isLod, LOD_EXIT_ZOOM);
    expect(isLod).toBe(true);
  });
});
