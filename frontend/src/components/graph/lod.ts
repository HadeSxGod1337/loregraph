// Below this zoom, card details (icon, badge, preview fields) are too small
// to read anyway — simplifying them to plain pills is what keeps panning
// smooth with hundreds of nodes on screen. Two thresholds (not one) add a
// dead zone so hovering right at the boundary doesn't flip back and forth.
export const LOD_ENTER_ZOOM = 0.35;
export const LOD_EXIT_ZOOM = 0.45;

/**
 * Hysteresis for the zoomed-out "level of detail" mode: only flips state
 * once zoom crosses the threshold *opposite* the current state, so hovering
 * exactly at one boundary can't flip-flop every frame. Pulled out of
 * GraphCanvas as a pure function so the dead-zone behavior itself — the part
 * that's easy to get subtly wrong — is unit-testable without mounting React
 * Flow.
 */
export function nextLodState(
  wasLod: boolean,
  zoom: number,
  enter: number = LOD_ENTER_ZOOM,
  exit: number = LOD_EXIT_ZOOM,
): boolean {
  if (wasLod && zoom > exit) return false;
  if (!wasLod && zoom < enter) return true;
  return wasLod;
}
