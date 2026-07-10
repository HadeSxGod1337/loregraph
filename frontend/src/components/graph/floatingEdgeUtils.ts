import { getStraightPath, Position, type InternalNode } from "@xyflow/react";

/**
 * Where the straight line between two node centers crosses `intersectionNode`'s
 * own rectangular border — the standard React Flow "floating edge" technique.
 * Used instead of fixed top/bottom handles so edges connect at whichever side
 * actually faces the other node, rather than looping around when nodes sit
 * side-by-side (as our radial layout frequently produces).
 */
function getNodeIntersection(
  intersectionNode: InternalNode,
  targetNode: InternalNode,
): { x: number; y: number } {
  const w = (intersectionNode.measured.width ?? 0) / 2;
  const h = (intersectionNode.measured.height ?? 0) / 2;
  const intersectionNodePosition = intersectionNode.internals.positionAbsolute;
  const targetPosition = targetNode.internals.positionAbsolute;

  const x2 = intersectionNodePosition.x + w;
  const y2 = intersectionNodePosition.y + h;
  const x1 = targetPosition.x + (targetNode.measured.width ?? 0) / 2;
  const y1 = targetPosition.y + (targetNode.measured.height ?? 0) / 2;

  const xx1 = (x1 - x2) / (2 * w) - (y1 - y2) / (2 * h);
  const yy1 = (x1 - x2) / (2 * w) + (y1 - y2) / (2 * h);
  const a = 1 / (Math.abs(xx1) + Math.abs(yy1) || 1);
  const xx3 = a * xx1;
  const yy3 = a * yy1;

  return {
    x: w * (xx3 + yy3) + x2,
    y: h * (-xx3 + yy3) + y2,
  };
}

function getEdgePosition(
  node: InternalNode,
  intersectionPoint: { x: number; y: number },
): Position {
  const nx = Math.round(node.internals.positionAbsolute.x);
  const ny = Math.round(node.internals.positionAbsolute.y);
  const px = Math.round(intersectionPoint.x);
  const py = Math.round(intersectionPoint.y);

  if (px <= nx + 1) return Position.Left;
  if (px >= nx + (node.measured.width ?? 0) - 1) return Position.Right;
  if (py <= ny + 1) return Position.Top;
  if (py >= ny + (node.measured.height ?? 0) - 1) return Position.Bottom;
  return Position.Top;
}

export function getEdgeParams(source: InternalNode, target: InternalNode) {
  const sourceIntersectionPoint = getNodeIntersection(source, target);
  const targetIntersectionPoint = getNodeIntersection(target, source);

  return {
    sx: sourceIntersectionPoint.x,
    sy: sourceIntersectionPoint.y,
    tx: targetIntersectionPoint.x,
    ty: targetIntersectionPoint.y,
    sourcePos: getEdgePosition(source, sourceIntersectionPoint),
    targetPos: getEdgePosition(target, targetIntersectionPoint),
  };
}

/**
 * When several edges connect the same pair of nodes (multiple relationship
 * types, or a bidirectional pair like A-knows->B plus B-knows->A), a straight
 * line between the same two border points makes them fully overlap — lines
 * and labels stack on top of each other illegibly. `offset` bows the path
 * away from the straight line by that many px (perpendicular to it, sign
 * picks the side), so each edge in the group gets its own visible arc.
 * offset === 0 keeps the plain straight path (the common single-edge case).
 */
export function getOffsetPath(
  sx: number,
  sy: number,
  tx: number,
  ty: number,
  offset: number,
): [path: string, labelX: number, labelY: number] {
  if (offset === 0) {
    const [path, labelX, labelY] = getStraightPath({
      sourceX: sx,
      sourceY: sy,
      targetX: tx,
      targetY: ty,
    });
    return [path, labelX, labelY];
  }

  const mx = (sx + tx) / 2;
  const my = (sy + ty) / 2;
  // Derive the perpendicular from a direction canonicalized to be independent
  // of which end is source vs target: for a reversed edge (B->A instead of
  // A->B) sx/tx are swapped, which would otherwise flip (nx, ny) and cancel
  // out the offset sign — landing both edges of a bidirectional pair on the
  // exact same control point instead of opposite sides.
  const forward = sx < tx || (sx === tx && sy <= ty);
  const dx = forward ? tx - sx : sx - tx;
  const dy = forward ? ty - sy : sy - ty;
  const length = Math.hypot(dx, dy) || 1;
  const nx = -dy / length;
  const ny = dx / length;
  const cx = mx + nx * offset;
  const cy = my + ny * offset;

  const path = `M ${sx},${sy} Q ${cx},${cy} ${tx},${ty}`;
  // Point at t=0.5 on the quadratic bezier — where the label sits.
  const labelX = 0.25 * sx + 0.5 * cx + 0.25 * tx;
  const labelY = 0.25 * sy + 0.5 * cy + 0.25 * ty;
  return [path, labelX, labelY];
}

/** Perpendicular offsets (px) for `count` parallel edges between one node
 * pair, spread symmetrically around the straight line (0 for a lone edge). */
export function edgeGroupOffsets(count: number, step = 46): number[] {
  if (count <= 1) return [0];
  return Array.from({ length: count }, (_, i) => (i - (count - 1) / 2) * step);
}
