import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Edge as FlowEdge,
  type Node as FlowNode,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo } from "react";

import { API_URL } from "../../api/client";
import type { Edge, Entity } from "../../api/types";
import { EntityNode, type EntityNodeData } from "./EntityNode";
import { FloatingEdge } from "./FloatingEdge";
import { computeRadialLayout } from "./layout";
import { getPreviewFields } from "./previewFields";

const nodeTypes = { entity: EntityNode };
const edgeTypes = { floating: FloatingEdge };

interface GraphCanvasProps {
  nodes: Entity[];
  edges: Edge[];
  rootId: string;
  selectedEntityId: string | null;
  onNodeSelect: (entityId: string) => void;
  onConnectNodes: (sourceId: string, targetId: string) => void;
  onEdgeSelect: (edgeId: string) => void;
  onPaneClick: () => void;
}

function toFlowNode(
  entity: Entity,
  position: { x: number; y: number },
  rootId: string,
  selectedEntityId: string | null,
): FlowNode<EntityNodeData> {
  return {
    id: entity.id,
    type: "entity",
    position,
    data: {
      label: entity.title,
      entityType: entity.type,
      isRoot: entity.id === rootId,
      isSelected: entity.id === selectedEntityId,
      iconUrl: entity.icon ? API_URL + entity.icon.url : null,
      previewFields: getPreviewFields(entity),
    },
  };
}

/**
 * Node positions live in React Flow's own controlled-state pattern
 * (`useNodesState` + `applyNodeChanges`), NOT recomputed from scratch every
 * render. That distinction matters a lot: recomputing the whole `nodes`
 * array via `.map()` on every drag frame — even though only one node's
 * position actually changes — hands React Flow a brand-new object
 * reference for every node each frame, and it diffs nodes by reference. It
 * read that as "everything changed" 60 times a second during a drag, which
 * is the flashing/flicker bug. `applyNodeChanges` instead patches only the
 * node(s) an event actually touched and keeps every other node's object
 * identity stable, so only the dragged node re-renders.
 *
 * The radial layout only seeds *initial* positions for nodes new to the
 * view; once a node has a position in this state, entity/selection updates
 * refresh its `data` in place without touching `position`, so dragging
 * sticks across re-renders. Resets when `GraphCanvas` remounts this
 * subtree via `key={rootId}` (new root = clean layout).
 */
function useSyncedFlowNodes(
  entities: Entity[],
  edges: Edge[],
  rootId: string,
  selectedEntityId: string | null,
) {
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<FlowNode<EntityNodeData>>([]);

  useEffect(() => {
    setFlowNodes((prev) => {
      const prevById = new Map(prev.map((n) => [n.id, n]));
      const autoPositions = computeRadialLayout(entities, edges, rootId);
      return entities.map((entity) => {
        const existingPosition = prevById.get(entity.id)?.position;
        const position = existingPosition ?? autoPositions.get(entity.id) ?? { x: 0, y: 0 };
        return toFlowNode(entity, position, rootId, selectedEntityId);
      });
    });
  }, [entities, edges, rootId, selectedEntityId, setFlowNodes]);

  return { flowNodes, onNodesChange };
}

function GraphCanvasInner({
  nodes,
  edges,
  rootId,
  selectedEntityId,
  onNodeSelect,
  onConnectNodes,
  onEdgeSelect,
  onPaneClick,
}: GraphCanvasProps) {
  const { fitView } = useReactFlow();
  const { flowNodes, onNodesChange } = useSyncedFlowNodes(
    nodes,
    edges,
    rootId,
    selectedEntityId,
  );

  const flowEdges: FlowEdge[] = useMemo(
    () =>
      edges.map((edge) => ({
        id: edge.id,
        source: edge.source_entity_id,
        target: edge.target_entity_id,
        type: "floating",
        label: edge.label ? `${edge.type} — ${edge.label}` : edge.type,
        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      })),
    [edges],
  );

  // Re-fits only when the node *set* changes (new root/depth/filter) — this
  // depends on `nodes` (the entity list prop), never on `flowNodes`/drag
  // state, so dragging never re-triggers a camera animation.
  useEffect(() => {
    const raf = requestAnimationFrame(() => fitView({ duration: 300, padding: 0.2 }));
    return () => cancelAnimationFrame(raf);
  }, [nodes, fitView]);

  return (
    <ReactFlow
      nodes={flowNodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={onNodesChange}
      onNodeClick={(_, node) => onNodeSelect(node.id)}
      onConnect={(c) => c.source && c.target && onConnectNodes(c.source, c.target)}
      onEdgeClick={(_, edge) => onEdgeSelect(edge.id)}
      onPaneClick={onPaneClick}
    >
      <Background color="var(--border)" gap={22} size={1} />
      <Controls />
    </ReactFlow>
  );
}

export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <div className="graph-canvas">
      <ReactFlowProvider key={props.rootId}>
        <GraphCanvasInner {...props} />
      </ReactFlowProvider>
    </div>
  );
}
