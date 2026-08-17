import { BaseEdge, EdgeLabelRenderer, useInternalNode, type EdgeProps } from "@xyflow/react";
import { memo, type CSSProperties } from "react";

import { useActiveRoot } from "./ActiveRootContext";
import { computeEdgeEmphasis, getEdgeParams, getOffsetPath } from "./floatingEdgeUtils";
import { useHoveredEntity } from "./HoveredEntityContext";
import { useSelectedEntity } from "./SelectedEntityContext";

export interface FloatingEdgeData extends Record<string, unknown> {
  offset?: number;
}

// Memoized for the same reason as EntityNode — with hundreds/thousands of
// edges on screen, an unmemoized custom edge re-renders on every store
// change React Flow re-evaluates it for, not just when its own endpoints move.
export const FloatingEdge = memo(function FloatingEdge({
  id,
  source,
  target,
  label,
  style,
  markerEnd,
  data,
}: EdgeProps) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  // Context reads, not `data` — same rationale as EntityNode's isSelected/
  // isRoot: hovering/selecting/changing root must only touch the few edges
  // actually incident to it, not rebuild the whole `edges` array (see
  // GraphCanvas.tsx's flowEdges memo, which depends on `edges` alone).
  const hoveredEntityId = useHoveredEntity();
  const selectedEntityId = useSelectedEntity();
  const rootId = useActiveRoot();

  if (!sourceNode || !targetNode) return null;

  const { sx, sy, tx, ty } = getEdgeParams(sourceNode, targetNode);
  const offset = (data as FloatingEdgeData | undefined)?.offset ?? 0;
  const [edgePath, labelX, labelY] = getOffsetPath(sx, sy, tx, ty, offset);
  const emphasis = computeEdgeEmphasis({
    sourceId: source,
    targetId: target,
    hoveredEntityId,
    selectedEntityId,
    rootId,
  });

  const pathStyle: CSSProperties = {
    ...style,
    transition: "opacity 0.15s ease, stroke-width 0.15s ease",
    ...(emphasis.dimmed ? { opacity: 0.35 } : undefined),
    ...(emphasis.emphasized ? { strokeWidth: 2.5 } : undefined),
  };
  const labelClassName = emphasis.emphasized
    ? "graph-edge-label graph-edge-label-emphasized"
    : emphasis.dimmed
      ? "graph-edge-label graph-edge-label-dimmed"
      : "graph-edge-label";

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={pathStyle} />
      {label && (
        <EdgeLabelRenderer>
          <div
            className={labelClassName}
            title={String(label)}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
});
