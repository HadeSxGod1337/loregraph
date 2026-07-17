import { Handle, Position, type NodeProps } from "@xyflow/react";
import { memo, type CSSProperties } from "react";

import { typeColor, typeSoftBackground } from "../../lib/typeColor";
import { useActiveRoot } from "./ActiveRootContext";
import { useSelectedEntity } from "./SelectedEntityContext";

export interface PreviewField {
  key: string;
  value: string;
}

export interface EntityNodeData extends Record<string, unknown> {
  label: string;
  entityType: string;
  iconUrl?: string | null;
  previewFields: PreviewField[];
}

// Zoomed-out simplification (hiding icon/badge/preview, dropping the
// clip-path) is applied via the `.react-flow-lod` ancestor class in App.css,
// not here — a single class toggle on the canvas root is far cheaper than
// every node independently subscribing to zoom and re-rendering a different
// JSX tree in the same frame (that was tried and measurably janky at a few
// hundred nodes; see GraphCanvas.tsx).
//
// Memoized: with hundreds/thousands of nodes on screen, an unmemoized custom
// node component re-renders on every store change React Flow's node wrapper
// re-evaluates (panning, other nodes' drags, selection elsewhere) even when
// this node's own `id`/`data` didn't change — React Flow's own performance
// guide calls this out explicitly for custom node/edge components.
export const EntityNode = memo(function EntityNode({ id, data }: NodeProps) {
  const { label, entityType, iconUrl, previewFields } = data as EntityNodeData;
  const isSelected = useSelectedEntity() === id;
  // Same rationale as isSelected: read from context, not `data`, so changing
  // root only re-renders the two affected nodes instead of rebuilding the
  // whole array (see GraphCanvas.tsx's useSyncedFlowNodes).
  const isRoot = useActiveRoot() === id;
  const color = typeColor(entityType);

  return (
    <div
      className={`entity-node${isRoot ? " entity-node-root" : ""}${isSelected ? " entity-node-selected" : ""}`}
      style={{ "--type-color": color } as CSSProperties}
    >
      {/* FloatingEdge computes its path from the nodes' measured bounds, not
          from handle position (see floatingEdgeUtils.ts) — so a single
          source + target pair (rather than one per side) draws identical
          edges regardless of which side of the card they sit on. Split
          top/bottom rather than stacked on the same spot purely for looks —
          one lone dot read oddly, two on opposite edges reads like a normal
          connectable node. Kept small and centered, NOT stretched over the
          card: React Flow tags every handle with its own `nodrag` class, so
          a handle covering the whole node would swallow the mousedown
          that's supposed to start repositioning the card (a bigger
          regression than the DOM savings are worth — dragging nodes is the
          exact interaction this pass is meant to keep smooth). */}
      <Handle type="target" position={Position.Top} className="entity-node-handle" isConnectable />
      <Handle type="source" position={Position.Bottom} className="entity-node-handle" isConnectable />
      {iconUrl && (
        <div className="entity-node-icon-slot">
          <img className="entity-node-icon" src={iconUrl} alt="" />
        </div>
      )}
      <div className="entity-node-info">
        <span
          className="entity-type-badge"
          style={{
            background: typeSoftBackground(entityType),
            color,
            borderColor: "transparent",
          }}
        >
          {entityType}
        </span>
        <span className="entity-node-title">{label}</span>
        {previewFields.length > 0 && (
          <div className="entity-node-preview">
            {previewFields.map((f) => (
              <span key={f.key} className="entity-node-preview-item">
                {f.key ? <b>{f.key}: </b> : null}
                {f.value}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
});
