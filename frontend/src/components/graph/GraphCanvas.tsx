import {
  Background,
  BackgroundVariant,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  useStore,
  type Edge as FlowEdge,
  type Node as FlowNode,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { API_URL } from "../../api/client";
import { entitiesApi, type PositionEntry } from "../../api/entities";
import type { Edge, Entity } from "../../api/types";
import { useDebouncedCallback } from "../../hooks/useDebouncedCallback";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { typeColor } from "../../lib/typeColor";
import { ActiveRootContext } from "./ActiveRootContext";
import { EntityNode, type EntityNodeData } from "./EntityNode";
import { FloatingEdge } from "./FloatingEdge";
import { edgeGroupOffsets } from "./floatingEdgeUtils";
import { HierarchyCollapseContext, type HierarchyCollapseState } from "./HierarchyCollapseContext";
import { HoveredEntityContext } from "./HoveredEntityContext";
import { computeForceLayout } from "./layout";
import { nextLodState } from "./lod";
import { getPreviewFields } from "./previewFields";
import { SelectedEntityContext } from "./SelectedEntityContext";

// Positions are saved on the server debounced by this much after the last
// drag event, so dragging one node around doesn't fire a request per frame.
const POSITION_SAVE_DEBOUNCE_MS = 500;
// React Flow's own default (0.5) doesn't let a large "All entities" world
// zoom out far enough to see everything at once.
const MIN_ZOOM = 0.05;
// Shared by the background pattern and snapGrid — grid lines are only a
// useful reference for where nodes will snap if both use the same spacing.
const GRID_SIZE = 22;

function minimapNodeColor(node: FlowNode<EntityNodeData>): string {
  return typeColor(node.data.entityType);
}

const nodeTypes = { entity: EntityNode };
const edgeTypes = { floating: FloatingEdge };
// Stable reference — an inline object literal here would give ReactFlow a
// new prop identity every render (see React Flow's memoization guidance).
const DEFAULT_EDGE_OPTIONS = { type: "floating" };

export interface CameraFocusRequest {
  entityId: string;
  /** Distinct per request so asking to re-focus the *same* entity twice in a
   * row still retriggers the effect (object/string equality alone wouldn't). */
  nonce: number;
}

/** One-shot camera/layout commands dispatched from the consolidated toolbar
 * (GraphControls) — a sibling component outside the ReactFlowProvider, so it
 * can't call useReactFlow() itself. Mirrors the focusRequest pattern above
 * rather than introducing a second way to reach into the canvas. */
export type GraphActionType = "zoomIn" | "zoomOut" | "fitView" | "resetLayout";

export interface GraphActionRequest {
  type: GraphActionType;
  nonce: number;
}

interface GraphCanvasProps {
  projectId: string;
  /** Already run through hierarchy-collapse visibility by GraphViewPage — a
   * node hidden by a collapsed branch simply isn't in this array (see
   * computeHierarchyVisibility in lib/hierarchy.ts). GraphCanvas itself
   * stays unaware hierarchy collapse exists: it just renders what it's
   * given, same as before that layer existed. */
  nodes: Entity[];
  edges: Edge[];
  rootId: string;
  depth: number;
  viewMode: "focused" | "all";
  selectedEntityId: string | null;
  /** Only present in "all" mode — the request to center the camera on one
   * entity without changing root (see EntityDetailPanel's "focus camera"
   * button). */
  focusRequest: CameraFocusRequest | null;
  actionRequest: GraphActionRequest | null;
  /** Freezes dragging/connecting/selecting nodes — the toolbar's "lock
   * positions" toggle, replacing the interactivity lock that used to live on
   * React Flow's default <Controls/>. */
  locked: boolean;
  /** Toolbar's grid toggle — swaps the background to a line grid and snaps
   * dragged nodes to it (see GRID_SIZE). */
  gridEnabled: boolean;
  /** Entity ids with at least one hierarchy child among `nodes` — which of
   * them get a collapse/expand chevron at all. Wider than `nodes` alone
   * would suggest nothing: a collapsed parent stays in `nodes` (collapsing
   * never hides the node itself), so this still needs to reach it. */
  hierarchyParentIds: ReadonlySet<string>;
  hierarchyCollapsedIds: ReadonlySet<string>;
  hierarchyHiddenCounts: ReadonlyMap<string, number>;
  onToggleHierarchyCollapse: (entityId: string) => void;
  onNodeSelect: (entityId: string) => void;
  onNodeSetRoot: (entityId: string) => void;
  onConnectNodes: (sourceId: string, targetId: string) => void;
  onEdgeSelect: (edgeId: string) => void;
  onPaneClick: () => void;
}

function toFlowNode(
  entity: Entity,
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
      previewFields: getPreviewFields(entity),
      revealed: entity.revealed_to_players,
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
 * Auto-layout only seeds positions for nodes new to the view; once a node
 * has a position in this state, entity updates refresh its `data` in place
 * without touching `position`, so dragging sticks across re-renders. Resets
 * when `GraphCanvas` remounts this subtree via `key` (Focused mode: new root
 * = clean layout) — the backend-saved position (`entity.pos_x`/`pos_y`,
 * global per entity) takes over at that point, so placement still survives
 * a root change. Selection and root are deliberately NOT part of this state
 * — see `SelectedEntityContext`/`ActiveRootContext` — so selecting a node or
 * changing root doesn't rebuild every node's object identity; in All mode
 * root changes constantly (that's the whole point of the "Active entity"
 * picker) while this effect must NOT rerun for it.
 *
 * `computeForceLayout` ticks across animation frames rather than blocking
 * (see layout.ts), so this effect is async — the `AbortController` cleanup
 * makes sure a stale computation (entities/edges changed again before the
 * previous run finished, e.g. rapid Focused/All toggling) never applies its
 * result after the fact.
 */
function useSyncedFlowNodes(entities: Entity[], edges: Edge[]) {
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<FlowNode<EntityNodeData>>([]);
  // Read inside the async effect below without making it a reactive
  // dependency — it only needs the latest value at the moment a run starts,
  // never a reason to retrigger (flowNodes changes on every drag, which must
  // NOT recompute layout).
  const flowNodesRef = useRef(flowNodes);
  flowNodesRef.current = flowNodes;

  useEffect(() => {
    const controller = new AbortController();

    async function run() {
      const prevById = new Map(flowNodesRef.current.map((n) => [n.id, n]));
      const anchored = new Map<string, { x: number; y: number }>();
      for (const entity of entities) {
        const existingPosition = prevById.get(entity.id)?.position;
        if (existingPosition) {
          anchored.set(entity.id, existingPosition);
        } else if (entity.pos_x != null && entity.pos_y != null) {
          anchored.set(entity.id, { x: entity.pos_x, y: entity.pos_y });
        }
      }
      const autoPositions = await computeForceLayout(entities, edges, anchored, controller.signal);
      if (controller.signal.aborted) return;
      setFlowNodes(
        entities.map((entity) => {
          const position = anchored.get(entity.id) ?? autoPositions.get(entity.id) ?? { x: 0, y: 0 };
          return toFlowNode(entity, position);
        }),
      );
    }
    void run();

    return () => controller.abort();
  }, [entities, edges, setFlowNodes]);

  return { flowNodes, setFlowNodes, onNodesChange };
}

function GraphCanvasInner({
  projectId,
  nodes,
  edges,
  rootId,
  depth,
  viewMode,
  selectedEntityId,
  focusRequest,
  actionRequest,
  locked,
  gridEnabled,
  hierarchyParentIds,
  hierarchyCollapsedIds,
  hierarchyHiddenCounts,
  onToggleHierarchyCollapse,
  onNodeSelect,
  onNodeSetRoot,
  onConnectNodes,
  onEdgeSelect,
  onPaneClick,
}: GraphCanvasProps) {
  const { t } = useTranslation();
  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const { flowNodes, setFlowNodes, onNodesChange } = useSyncedFlowNodes(nodes, edges);
  // Read inside the root/depth fit effect below without making it a
  // dependency — switching Focused/All alone must not retrigger that effect
  // (see its own comment), only change what it *does* the next time rootId
  // or depth actually changes.
  const viewModeRef = useRef(viewMode);
  viewModeRef.current = viewMode;

  const savePositions = useDebouncedCallback((positions: PositionEntry[]) => {
    entitiesApi.updatePositions(projectId, positions).catch((err: unknown) => {
      console.error("Failed to save node positions:", err);
    });
  }, POSITION_SAVE_DEBOUNCE_MS);

  const handleNodeDragStop = useCallback(
    (_event: MouseEvent | TouchEvent, node: FlowNode<EntityNodeData>) => {
      savePositions([{ entity_id: node.id, pos_x: node.position.x, pos_y: node.position.y }]);
    },
    [savePositions],
  );

  // Resetting overwrites every manually-dragged position in view — the same
  // kind of one-way, hard-to-undo action as deleting an entity, so it gets
  // the same confirm-first treatment.
  const [confirmingReset, setConfirmingReset] = useState(false);

  // Recomputes a fresh layout for every node currently in view (no anchors,
  // unlike the auto-layout-for-new-nodes path above) and persists it
  // immediately — this is an explicit one-off user action, not a debounced
  // drag, so it shouldn't wait.
  const handleResetLayout = useCallback(async () => {
    const layout = await computeForceLayout(nodes, edges, new Map());
    setFlowNodes((prev) =>
      prev.map((n) => {
        const position = layout.get(n.id);
        return position ? { ...n, position } : n;
      }),
    );
    const positions: PositionEntry[] = [];
    for (const node of nodes) {
      const position = layout.get(node.id);
      if (position) positions.push({ entity_id: node.id, pos_x: position.x, pos_y: position.y });
    }
    if (positions.length > 0) {
      entitiesApi.updatePositions(projectId, positions).catch((err: unknown) => {
        console.error("Failed to save reset layout positions:", err);
      });
    }
    // Without this, nodes that had drifted far from the viewport (e.g. after
    // manual dragging) land in their new spread-out positions off-screen,
    // leaving the canvas looking empty until the user manually pans/uses the
    // minimap to find them.
    requestAnimationFrame(() => fitView({ duration: 300, padding: 0.2 }));
  }, [nodes, edges, projectId, setFlowNodes, fitView]);

  // Edges sharing the same pair of nodes (multiple relationship types, or a
  // bidirectional pair) would otherwise draw as fully overlapping lines with
  // stacked labels — give each edge in such a group its own offset so
  // FloatingEdge can bow them apart into separate visible arcs.
  const flowEdges: FlowEdge[] = useMemo(() => {
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

  // Re-fits only on an actual change of *focus* (root or depth) — not on
  // `nodes` generally, so toggling Focused/All doesn't yank the camera
  // through an animated zoom-to-fit-everything at the same moment hundreds
  // of new nodes are being laid out and mounted (that combination is what
  // made switching to "All" feel like it dropped frames). Switching modes
  // alone (rootId/depth unchanged) leaves the viewport exactly where the
  // user left it.
  //
  // What the fit actually *does* differs by mode, read from a ref so mode
  // alone can't retrigger this: in Focused mode the visible BFS neighborhood
  // just changed, so fit everything (animated — it's a real change of what's
  // on screen). In All mode the node set never changes when the active
  // entity does, so fit-everything would be wrong — just pan to that one
  // entity, and instantly (no `duration`): this fires on every "Active
  // entity" change, and an animated fly-through each time reads as
  // gratuitous motion rather than useful feedback once you're just hopping
  // between entities that are already all on screen.
  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      if (viewModeRef.current === "all") {
        if (rootId) {
          fitView({ nodes: [{ id: rootId }], padding: 0.5, maxZoom: 1.2 });
        }
      } else {
        fitView({ duration: 300, padding: 0.2 });
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [rootId, depth, fitView]);

  // The detail panel's standalone "focus camera" action — centers on one
  // entity without touching `rootId` at all. Instant, same reasoning as above.
  useEffect(() => {
    if (!focusRequest) return;
    const raf = requestAnimationFrame(() =>
      fitView({ nodes: [{ id: focusRequest.entityId }], padding: 0.5, maxZoom: 1.2 }),
    );
    return () => cancelAnimationFrame(raf);
  }, [focusRequest, fitView]);

  // Zoom/fit/reset-layout buttons live in the toolbar (GraphControls),
  // outside the ReactFlowProvider, so they can't call useReactFlow()
  // directly — see the GraphActionRequest comment above. "resetLayout" only
  // opens the same confirm dialog the effect below already guards; the
  // actual layout recompute stays gated behind that confirmation either way.
  useEffect(() => {
    if (!actionRequest) return;
    switch (actionRequest.type) {
      case "zoomIn":
        zoomIn({ duration: 200 });
        break;
      case "zoomOut":
        zoomOut({ duration: 200 });
        break;
      case "fitView":
        fitView({ duration: 300, padding: 0.2 });
        break;
      case "resetLayout":
        setConfirmingReset(true);
        break;
    }
  }, [actionRequest, zoomIn, zoomOut, fitView]);

  // Tracked once here (not per-node) and applied as a single class toggle —
  // see the .react-flow-lod rules in App.css.
  const zoomLevel = useStore((s) => s.transform[2]);
  const [isLod, setIsLod] = useState(false);
  useEffect(() => {
    setIsLod((prev) => nextLodState(prev, zoomLevel));
  }, [zoomLevel]);

  // Which entity (if any) the pointer is currently over — read by
  // FloatingEdge to spotlight that node's own relationships and fade the
  // rest (see HoveredEntityContext). Node-granularity only: these are
  // discrete enter/leave events at whatever rate the pointer crosses node
  // boundaries, not a per-frame stream like drag, so re-rendering the edges
  // that read this context is cheap even with hundreds of them on screen.
  const [hoveredEntityId, setHoveredEntityId] = useState<string | null>(null);
  const handleNodeMouseEnter = useCallback(
    (_: React.MouseEvent, node: FlowNode<EntityNodeData>) => setHoveredEntityId(node.id),
    [],
  );
  const handleNodeMouseLeave = useCallback(() => setHoveredEntityId(null), []);

  // New object identity on every render would defeat the point of reading
  // this from context (see HierarchyCollapseContext) — every EntityNode
  // would re-render on every unrelated GraphCanvasInner render, drag frames
  // included. Memoized so it only changes when one of these four actually does.
  const hierarchyCollapseState: HierarchyCollapseState = useMemo(
    () => ({
      parentIds: hierarchyParentIds,
      collapsedIds: hierarchyCollapsedIds,
      hiddenCounts: hierarchyHiddenCounts,
      onToggle: onToggleHierarchyCollapse,
    }),
    [hierarchyParentIds, hierarchyCollapsedIds, hierarchyHiddenCounts, onToggleHierarchyCollapse],
  );

  return (
    <SelectedEntityContext.Provider value={selectedEntityId}>
      <ActiveRootContext.Provider value={rootId}>
        <HoveredEntityContext.Provider value={hoveredEntityId}>
          <HierarchyCollapseContext.Provider value={hierarchyCollapseState}>
            <ReactFlow
              className={isLod ? "react-flow-lod" : undefined}
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onNodesChange={onNodesChange}
              onNodeClick={(_, node) => onNodeSelect(node.id)}
              onNodeDoubleClick={(_, node) => onNodeSetRoot(node.id)}
              onNodeDragStop={handleNodeDragStop}
              onNodeMouseEnter={handleNodeMouseEnter}
              onNodeMouseLeave={handleNodeMouseLeave}
              onConnect={(c) => c.source && c.target && onConnectNodes(c.source, c.target)}
              onEdgeClick={(_, edge) => onEdgeSelect(edge.id)}
              onPaneClick={onPaneClick}
              connectionRadius={120}
              connectOnClick
              defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
              // Skips rendering nodes/edges outside the viewport — the "All
              // entities" mode can put hundreds of nodes on canvas at once.
              onlyRenderVisibleElements
              minZoom={MIN_ZOOM}
              // "Lock positions" toolbar toggle — same trio React Flow's own
              // default <Controls/> interactivity lock used to drive, now
              // surfaced through GraphControls instead (see `locked` above).
              // Collapse/expand is a plain DOM button inside EntityNode, not
              // routed through any of these three — it stays clickable while
              // locked, matching "lock is about layout/drag, not visibility".
              nodesDraggable={!locked}
              nodesConnectable={!locked}
              elementsSelectable={!locked}
              // Grid toggle — snapping only kicks in on the next manual drag;
              // it never retroactively moves nodes that are already placed
              // (auto-layout's continuous coordinates included), so flipping
              // this on mid-session doesn't rearrange anything by itself.
              snapToGrid={gridEnabled}
              snapGrid={[GRID_SIZE, GRID_SIZE]}
            >
              <Background
                color="var(--border)"
                gap={GRID_SIZE}
                size={1}
                variant={gridEnabled ? BackgroundVariant.Lines : BackgroundVariant.Dots}
              />
              <MiniMap pannable zoomable nodeColor={minimapNodeColor} nodeStrokeWidth={0} />
            </ReactFlow>
            {confirmingReset && (
              <ConfirmDialog
                title={t("graph.resetLayoutConfirmTitle")}
                body={t("graph.resetLayoutConfirmBody")}
                confirmLabel={t("graph.resetLayout")}
                onConfirm={() => {
                  setConfirmingReset(false);
                  void handleResetLayout();
                }}
                onCancel={() => setConfirmingReset(false)}
              />
            )}
          </HierarchyCollapseContext.Provider>
        </HoveredEntityContext.Provider>
      </ActiveRootContext.Provider>
    </SelectedEntityContext.Provider>
  );
}

export function GraphCanvas(props: GraphCanvasProps) {
  // In Focused mode a new root is a genuinely different BFS neighborhood, so
  // remounting for a clean layout is correct (see useSyncedFlowNodes). In
  // All mode the node set never changes when the active entity does — the
  // key must stay stable there, or every root change tears down and rebuilds
  // the whole canvas (all nodes' DOM + the layout effect) just to move a
  // camera, which is what made switching the "Active entity" feel like a
  // page reload.
  const canvasKey = props.viewMode === "focused" ? props.rootId : "all";
  return (
    <div className="graph-canvas flow-surface">
      <ReactFlowProvider key={canvasKey}>
        <GraphCanvasInner {...props} />
      </ReactFlowProvider>
    </div>
  );
}
