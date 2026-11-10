import { useLayoutEffect } from "react";
import type { RefObject } from "react";

export interface AutoGrowLimits {
  minHeightPx: number;
  maxHeightPx: number;
}

/** Clamps a textarea's natural content height to the configured bounds — the
 * part worth unit-testing without a DOM. */
export function clampTextareaHeight(scrollHeightPx: number, limits: AutoGrowLimits): number {
  return Math.min(Math.max(scrollHeightPx, limits.minHeightPx), limits.maxHeightPx);
}

/** Grows a textarea with its content up to maxHeightPx, then leaves it to
 * scroll internally instead of pushing the rest of the composer around.
 * Bounds are taken as separate scalar params rather than one options object
 * so the effect's dependency array can list them directly — an inline
 * `{ minHeightPx, maxHeightPx }` literal from the caller would otherwise be a
 * new object every render and rerun the effect unconditionally. */
export function useAutoGrowTextarea(
  ref: RefObject<HTMLTextAreaElement | null>,
  value: string,
  minHeightPx: number,
  maxHeightPx: number,
) {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Collapse first so scrollHeight reflects the current content instead of
    // whatever height was set on the previous render (it never shrinks
    // otherwise — scrollHeight can't go below the box's own height).
    el.style.height = "auto";
    const next = clampTextareaHeight(el.scrollHeight, { minHeightPx, maxHeightPx });
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > maxHeightPx ? "auto" : "hidden";
  }, [ref, value, minHeightPx, maxHeightPx]);
}
