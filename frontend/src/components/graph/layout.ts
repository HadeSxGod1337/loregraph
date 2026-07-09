import type { Edge, Entity } from "../../api/types";

// Cards are 220px wide horizontal rectangles now (not the old ~110px compact
// cards) — needs enough spacing for a full card width plus edge-label
// breathing room between rings, or labels/cards start overlapping.
const RING_SPACING = 340;

/** BFS-ring layout: root at the center, each hop distance forms a ring. */
export function computeRadialLayout(
  nodes: Entity[],
  edges: Edge[],
  rootId: string,
): Map<string, { x: number; y: number }> {
  const adjacency = new Map<string, string[]>();
  const link = (from: string, to: string) => {
    const neighbors = adjacency.get(from);
    if (neighbors) neighbors.push(to);
    else adjacency.set(from, [to]);
  };
  for (const edge of edges) {
    link(edge.source_entity_id, edge.target_entity_id);
    link(edge.target_entity_id, edge.source_entity_id);
  }

  const distances = new Map<string, number>([[rootId, 0]]);
  const queue: string[] = [rootId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    const currentDistance = distances.get(current)!;
    for (const neighborId of adjacency.get(current) ?? []) {
      if (!distances.has(neighborId)) {
        distances.set(neighborId, currentDistance + 1);
        queue.push(neighborId);
      }
    }
  }

  const rings = new Map<number, string[]>();
  for (const node of nodes) {
    const distance = distances.get(node.id) ?? 0;
    const ring = rings.get(distance);
    if (ring) ring.push(node.id);
    else rings.set(distance, [node.id]);
  }

  const positions = new Map<string, { x: number; y: number }>();
  for (const [distance, ids] of rings) {
    if (distance === 0) {
      positions.set(ids[0], { x: 0, y: 0 });
      continue;
    }
    const radius = distance * RING_SPACING;
    ids.forEach((id, i) => {
      const angle = (2 * Math.PI * i) / ids.length;
      positions.set(id, { x: radius * Math.cos(angle), y: radius * Math.sin(angle) });
    });
  }
  return positions;
}
