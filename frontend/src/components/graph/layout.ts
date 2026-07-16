import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationNodeDatum,
} from "d3-force";

import type { Edge, Entity } from "../../api/types";

// Cards are 220px wide horizontal rectangles — spacing needs enough room for
// a full card width plus edge-label breathing room, or cards start
// overlapping.
const LINK_DISTANCE = 250;
const CHARGE_STRENGTH = -500;
const COLLISION_RADIUS = 150;
// Total ticks needed for the layout to settle. Run synchronously, 300 ticks
// over a few hundred nodes measures ~700ms of unbroken main-thread work —
// long enough to freeze the tab (no paint, no input) for the whole stretch.
// Ticking is instead chunked across animation frames (see TICKS_PER_FRAME)
// so the browser stays responsive throughout, even though the wall-clock
// time to finish is about the same.
const SIMULATION_TICKS = 300;
const TICKS_PER_FRAME = 5;
// "All entities" mode can contain several relationship webs with no edge
// between them at all (e.g. two unrelated adventuring parties). Each gets
// its own grid cell to steer toward, so unrelated clusters spread out
// instead of drifting into or on top of each other.
const COMPONENT_GRID_CELL_SIZE = 900;
// forceCollide already guarantees no two nodes ever overlap regardless of
// component — this force is purely about grouping, not collision safety.
// Measured against a seeded ~550-node/18-component world: much below this,
// the grid target loses to global charge repulsion and unrelated clusters'
// centroids can end up nearly coincident; much above it, the pull toward a
// rigid grid point measurably fights the organic within-component layout
// without actually reducing worst-case node-to-node distance any further
// (that floor is set by forceCollide, not by this force).
const COMPONENT_STEER_STRENGTH = 0.15;

interface ForceNode extends SimulationNodeDatum {
  id: string;
}

interface ForceLink {
  source: string;
  target: string;
}

/** Groups of node ids reachable from one another via `edges` — a graph with
 * no edge at all between two nodes has them in separate groups. */
function computeConnectedComponents(nodeIds: string[], edges: Edge[]): string[][] {
  const adjacency = new Map<string, string[]>();
  const link = (a: string, b: string) => {
    const neighbors = adjacency.get(a);
    if (neighbors) neighbors.push(b);
    else adjacency.set(a, [b]);
  };
  for (const edge of edges) {
    link(edge.source_entity_id, edge.target_entity_id);
    link(edge.target_entity_id, edge.source_entity_id);
  }

  const visited = new Set<string>();
  const components: string[][] = [];
  for (const startId of nodeIds) {
    if (visited.has(startId)) continue;
    const component: string[] = [];
    const queue = [startId];
    visited.add(startId);
    while (queue.length > 0) {
      const current = queue.shift()!;
      component.push(current);
      for (const neighbor of adjacency.get(current) ?? []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    }
    components.push(component);
  }
  return components;
}

/** One steering target per node: which grid cell its connected component
 * should settle around, laid out roughly centered on the origin. */
function componentSteeringTargets(
  nodeIds: string[],
  edges: Edge[],
): Map<string, { x: number; y: number }> | null {
  const components = computeConnectedComponents(nodeIds, edges);
  if (components.length <= 1) return null;

  const cols = Math.ceil(Math.sqrt(components.length));
  const rows = Math.ceil(components.length / cols);
  const targets = new Map<string, { x: number; y: number }>();
  components.forEach((component, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const center = {
      x: (col - (cols - 1) / 2) * COMPONENT_GRID_CELL_SIZE,
      y: (row - (rows - 1) / 2) * COMPONENT_GRID_CELL_SIZE,
    };
    for (const id of component) targets.set(id, center);
  });
  return targets;
}

/**
 * Force-directed layout for nodes that don't have a saved position yet.
 * `anchored` (already-placed nodes, from a drag or a prior save) is fed into
 * the simulation as fixed points (`fx`/`fy`), not excluded — new nodes then
 * settle near their real neighbors instead of being computed in an isolated
 * coordinate space centered on the origin. Returns positions only for the
 * nodes that needed placing.
 *
 * Ticks in small batches across animation frames rather than all at once —
 * see SIMULATION_TICKS — so callers should `await` this instead of expecting
 * a synchronous result. `signal` lets a caller abandon a stale computation
 * (e.g. the entity set changed again before this one finished) without it
 * still clobbering state after the fact.
 */
export async function computeForceLayout(
  nodes: Entity[],
  edges: Edge[],
  anchored: Map<string, { x: number; y: number }>,
  signal?: AbortSignal,
): Promise<Map<string, { x: number; y: number }>> {
  const unplacedIds = new Set(
    nodes.map((n) => n.id).filter((id) => !anchored.has(id)),
  );
  if (unplacedIds.size === 0) return new Map();

  const d3Nodes: ForceNode[] = nodes.map((n) => {
    const anchor = anchored.get(n.id);
    return anchor ? { id: n.id, x: anchor.x, y: anchor.y, fx: anchor.x, fy: anchor.y } : { id: n.id };
  });
  const d3Links: ForceLink[] = edges.map((e) => ({
    source: e.source_entity_id,
    target: e.target_entity_id,
  }));

  const simulation = forceSimulation(d3Nodes)
    .force(
      "link",
      forceLink<ForceNode, ForceLink>(d3Links)
        .id((d) => d.id)
        .distance(LINK_DISTANCE),
    )
    .force("charge", forceManyBody().strength(CHARGE_STRENGTH))
    .force("collision", forceCollide(COLLISION_RADIUS))
    .stop();

  // Centering (and component grid-steering, below) only make sense for a
  // fully-fresh layout: once any node is anchored, its real position already
  // anchors its whole connected component somewhere on the canvas, and
  // pulling new nodes toward a synthetic grid slot instead would fight the
  // link force trying to keep them near their (possibly far-from-origin)
  // anchored neighbors.
  if (anchored.size === 0) {
    simulation.force("center", forceCenter(0, 0));

    const steeringTargets = componentSteeringTargets(
      nodes.map((n) => n.id),
      edges,
    );
    if (steeringTargets) {
      simulation
        .force(
          "componentX",
          forceX<ForceNode>((d) => steeringTargets.get(d.id)?.x ?? 0).strength(
            COMPONENT_STEER_STRENGTH,
          ),
        )
        .force(
          "componentY",
          forceY<ForceNode>((d) => steeringTargets.get(d.id)?.y ?? 0).strength(
            COMPONENT_STEER_STRENGTH,
          ),
        );
    }
  }

  let ticksDone = 0;
  await new Promise<void>((resolve) => {
    function step() {
      if (signal?.aborted) {
        resolve();
        return;
      }
      const remaining = SIMULATION_TICKS - ticksDone;
      for (let i = 0; i < Math.min(TICKS_PER_FRAME, remaining); i++) simulation.tick();
      ticksDone += TICKS_PER_FRAME;
      if (ticksDone < SIMULATION_TICKS) requestAnimationFrame(step);
      else resolve();
    }
    requestAnimationFrame(step);
  });
  if (signal?.aborted) return new Map();

  const positions = new Map<string, { x: number; y: number }>();
  for (const node of d3Nodes) {
    if (!unplacedIds.has(node.id)) continue;
    positions.set(node.id, { x: node.x ?? 0, y: node.y ?? 0 });
  }
  return positions;
}
