import { BaseEdge, EdgeLabelRenderer, useInternalNode, type EdgeProps } from "@xyflow/react";

import { getEdgeParams, getOffsetPath } from "./floatingEdgeUtils";

export interface FloatingEdgeData extends Record<string, unknown> {
  offset?: number;
}

export function FloatingEdge({
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

  if (!sourceNode || !targetNode) return null;

  const { sx, sy, tx, ty } = getEdgeParams(sourceNode, targetNode);
  const offset = (data as FloatingEdgeData | undefined)?.offset ?? 0;
  const [edgePath, labelX, labelY] = getOffsetPath(sx, sy, tx, ty, offset);

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      {label && (
        <EdgeLabelRenderer>
          <div
            className="graph-edge-label"
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
}
