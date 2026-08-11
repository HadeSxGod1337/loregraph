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

import { API_URL } from "../api/client";
import type { Edge, Entity, PlayerEntity } from "../api/types";
import { ActiveRootContext } from "../components/graph/ActiveRootContext";
import { EntityNode, type EntityNodeData } from "../components/graph/EntityNode";
import { FloatingEdge } from "../components/graph/FloatingEdge";
import { edgeGroupOffsets } from "../components/graph/floatingEdgeUtils";
import { computeForceLayout } from "../components/graph/layout";
import { SelectedEntityContext } from "../components/graph/SelectedEntityContext";
import { getPlayPreviewFields } from "./playPreviewFields";

const MIN_ZOOM = 0.05;
const nodeTypes = { entity: EntityNode };
const edgeTypes = { floating: FloatingEdge };
const DEFAULT_EDGE_OPTIONS = { type: "floating" };

// Player entities carry only an id that the layout cares about; this narrows
// the shape computeForceLayout needs without pretending to be a full Entity.
function asLayoutNodes(nodes: PlayerEntity[]): Entity[] {
  return nodes.map((n) => ({ id: n.id }) as Entity);
}

function toFlowNode(
  entity: PlayerEntity,
  position: { x: number; y: number },
): FlowNode<EntityNodeData> {
  return {
    id: entity.id,
    type: "entity",
    position,
    data: {
      label: entity.title,
      entityType: entity.type,
      iconUrl: entity.icon ? API_URL + entity.icon.url : null,
      previewFields: getPlayPreviewFields(entity),
    },
  };
}

function Canvas({
  nodes,
  edges,
  onOpen,
}: {
  nodes: PlayerEntity[];
  edges: Edge[];
  onOpen: (entityId: string) => void;
}) {
  const [flowNodes, setFlowNodes, onNodesChange] =
    useNodesState<FlowNode<EntityNodeData>>([]);
  const { fitView } = useReactFlow();

  useEffect(() => {
    let cancelled = false;
    const anchored = new Map<string, { x: number; y: number }>();
    for (const n of nodes) {
      if (n.pos_x !== null && n.pos_y !== null) {
        anchored.set(n.id, { x: n.pos_x, y: n.pos_y });
      }
    }
    void computeForceLayout(asLayoutNodes(nodes), edges, anchored).then(
      (computed) => {
        if (cancelled) return;
        setFlowNodes(
          nodes.map((n) =>
            toFlowNode(
              n,
              anchored.get(n.id) ?? computed.get(n.id) ?? { x: 0, y: 0 },
            ),
          ),
        );
        requestAnimationFrame(() => fitView({ duration: 300, padding: 0.2 }));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [nodes, edges, setFlowNodes, fitView]);

  const flowEdges = useMemo<FlowEdge[]>(() => {
    const groupIds = new Map<string, string[]>();
    for (const edge of edges) {
      const key = [edge.source_entity_id, edge.target_entity_id].sort().join("|");
      const group = groupIds.get(key);
      if (group) group.push(edge.id);
      else groupIds.set(key, [edge.id]);
    }
    const offsetByEdgeId = new Map<string, number>();
    for (const ids of groupIds.values()) {
      const offsets = edgeGroupOffsets(ids.length);
      ids.forEach((id, i) => offsetByEdgeId.set(id, offsets[i]));
    }
    return edges.map((edge) => ({
      id: edge.id,
      source: edge.source_entity_id,
      target: edge.target_entity_id,
      type: "floating",
      label: edge.label ? `${edge.type} — ${edge.label}` : edge.type,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      data: { offset: offsetByEdgeId.get(edge.id) ?? 0 },
    }));
  }, [edges]);

  return (
    // ActiveRootContext is "" (players have no root/focus concept). Nodes are
    // draggable for local arranging only — nothing is persisted, so no
    // onNodeDragStop, onConnect, or onNodesChange write-back to the server.
    <ActiveRootContext.Provider value="">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodesChange={onNodesChange}
        onNodeClick={(_e, node) => onOpen(node.id)}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
        nodesConnectable={false}
        minZoom={MIN_ZOOM}
        fitView
      >
        {/* Same grid as the DM board — the stock <Background /> defaults to a
            light-mode grey that reads as noise on this theme. */}
        <Background color="var(--border)" gap={22} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </ActiveRootContext.Provider>
  );
}

/** Read-only board for players. Reuses the DM node/edge rendering but none of
 * the write paths — a separate component rather than five readOnly flags
 * threaded through the 400-line DM canvas. Clicking a node opens its card. */
export function PlayBoardCanvas({
  nodes,
  edges,
  onOpen,
}: {
  nodes: PlayerEntity[];
  edges: Edge[];
  onOpen: (entityId: string) => void;
}) {
  return (
    // No selection concept on the player board — a click navigates to the card.
    <SelectedEntityContext.Provider value={null}>
      <ReactFlowProvider>
        <Canvas nodes={nodes} edges={edges} onOpen={onOpen} />
      </ReactFlowProvider>
    </SelectedEntityContext.Provider>
  );
}
