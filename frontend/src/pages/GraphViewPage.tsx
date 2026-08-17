import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { apiClient } from "../api/client";
import type { Edge, Entity } from "../api/types";
import { AssistantPanel } from "../components/assistant/AssistantPanel";
import { Icon } from "../components/ui/Icon";
import { EntityNavigationContext } from "../components/EntityNavigationContext";
import { EdgeEditPopover } from "../components/graph/EdgeEditPopover";
import { EdgeQuickForm } from "../components/graph/EdgeQuickForm";
import { EntityDetailPanel } from "../components/graph/EntityDetailPanel";
import {
  GraphCanvas,
  type CameraFocusRequest,
  type GraphActionRequest,
  type GraphActionType,
} from "../components/graph/GraphCanvas";
import { GraphControls, type GraphViewMode } from "../components/graph/GraphControls";
import { GraphCreateEntityButton } from "../components/graph/GraphCreateEntityButton";
import { useEntities } from "../hooks/useEntities";
import { useGraphHierarchyCollapse } from "../hooks/useGraphHierarchyCollapse";
import { useHierarchyConfig } from "../hooks/useHierarchyConfig";
import { useSubgraph } from "../hooks/useSubgraph";
import { buildHierarchy, computeHierarchyVisibility, filterVisibleEdges } from "../lib/hierarchy";

interface PendingConnection {
  sourceId: string;
  targetId: string;
}

// Above this, "All entities" mode shows a dismissible nudge toward Focused
// mode — not a hard cap, just a hint once a world gets large.
const LARGE_WORLD_NOTICE_THRESHOLD = 500;

export function GraphViewPage() {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();
  const { data: entities } = useEntities(projectId!);
  // Same containment vocabulary and pure forest utilities as the Entities
  // list page (see lib/hierarchy.ts) — the graph reads the project's
  // hierarchy edge types, it doesn't invent a second grouping model.
  const { config: hierarchyConfig } = useHierarchyConfig(projectId!);
  const graphCollapse = useGraphHierarchyCollapse(projectId!);
  const [rootId, setRootId] = useState("");
  const [depth, setDepth] = useState(2);
  const [edgeTypes, setEdgeTypes] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<GraphViewMode>("all");
  const [largeWorldNoticeDismissed, setLargeWorldNoticeDismissed] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [focusRequest, setFocusRequest] = useState<CameraFocusRequest | null>(null);
  const [actionRequest, setActionRequest] = useState<GraphActionRequest | null>(null);
  const [locked, setLocked] = useState(false);
  const [gridEnabled, setGridEnabled] = useState(false);
  const [pendingConnection, setPendingConnection] = useState<PendingConnection | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  // Newly created entities that aren't yet connected to the graph via edges.
  // They appear as isolated nodes; once an edge is created, the backend
  // includes them in the subgraph and we drop them from this local state.
  const [tempEntities, setTempEntities] = useState<Entity[]>([]);
  const isEmptyWorld = entities !== undefined && entities.length === 0;
  // null = no explicit choice yet: an empty world opens the assistant by
  // itself ("start here"), but the user can still close it.
  const [assistantOpen, setAssistantOpen] = useState<boolean | null>(null);
  const assistantVisible = assistantOpen ?? isEmptyWorld;

  const { data: allEdges } = useQuery({
    queryKey: ["edges", projectId],
    queryFn: () => apiClient.get<Edge[]>(`/api/projects/${projectId}/edges`),
  });

  // Default root: last one viewed in this project, else the most connected
  // entity — the graph should show something on open, not an empty prompt.
  const autoRootApplied = useRef(false);

  // The route reuses this component instance across projects (no key=):
  // per-project state must reset on switch or project A's root leaks into B.
  useEffect(() => {
    autoRootApplied.current = false;
    setRootId("");
    setSelectedEntityId(null);
    setSelectedEdgeId(null);
    setTempEntities([]);
    setViewMode("all");
    setLargeWorldNoticeDismissed(false);
    setLocked(false);
    setGridEnabled(false);
  }, [projectId]);

  // If the current root was deleted, fall back to auto-picking a new one.
  useEffect(() => {
    if (rootId && entities && !entities.some((entity) => entity.id === rootId)) {
      autoRootApplied.current = false;
      setRootId("");
    }
  }, [rootId, entities]);

  useEffect(() => {
    if (autoRootApplied.current || rootId || !entities?.length || !allEdges) return;
    autoRootApplied.current = true;
    const saved = localStorage.getItem(`loregraph:last-root:${projectId}`);
    if (saved && entities.some((entity) => entity.id === saved)) {
      setRootId(saved);
      return;
    }
    const degree = new Map<string, number>();
    for (const edge of allEdges) {
      degree.set(edge.source_entity_id, (degree.get(edge.source_entity_id) ?? 0) + 1);
      degree.set(edge.target_entity_id, (degree.get(edge.target_entity_id) ?? 0) + 1);
    }
    const best = [...entities].sort(
      (a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0),
    )[0];
    setRootId(best.id);
  }, [rootId, entities, allEdges, projectId]);

  function changeRoot(id: string) {
    setRootId(id);
    if (id) localStorage.setItem(`loregraph:last-root:${projectId}`, id);
  }

  // "Focus camera" — centers the viewport on an entity without touching
  // root. `nonce` guarantees the request is seen as new even when the user
  // asks to re-focus the entity they're already centered on.
  function focusCameraOn(id: string) {
    setFocusRequest({ entityId: id, nonce: Date.now() });
  }

  // Toolbar zoom/fit/reset-layout buttons — see GraphActionRequest.
  function dispatchGraphAction(type: GraphActionType) {
    setActionRequest({ type, nonce: Date.now() });
  }

  // Toolbar "center view" — whatever's selected is more useful to re-center
  // on than the root/active entity once something's actually being looked
  // at, falling back to root when nothing is selected. No-ops on an empty
  // canvas (neither is set yet).
  function centerView() {
    const target = selectedEntityId ?? rootId;
    if (target) focusCameraOn(target);
  }

  const availableEdgeTypes = useMemo(
    () => [...new Set((allEdges ?? []).map((edge) => edge.type))].sort(),
    [allEdges],
  );

  // Only queried in Focused mode — "All" renders straight from `entities` /
  // `allEdges`, both already fetched unconditionally above.
  const { data: subgraph, isLoading } = useSubgraph(
    projectId!,
    viewMode === "focused" ? rootId || undefined : undefined,
    depth,
    edgeTypes.length > 0 ? edgeTypes : undefined,
  );

  // Merge subgraph nodes with temp (newly created, not yet connected) entities.
  const focusedNodes = useMemo(() => {
    if (!subgraph) return tempEntities;
    const ids = new Set(subgraph.nodes.map((n) => n.id));
    const orphans = tempEntities.filter((e) => !ids.has(e.id));
    return orphans.length > 0 ? [...subgraph.nodes, ...orphans] : subgraph.nodes;
  }, [subgraph, tempEntities]);

  // "All" mode needs no BFS/tempEntities merge — `entities` already includes
  // every entity in the project regardless of whether it has any edges yet.
  const allModeEdges = useMemo(() => {
    if (edgeTypes.length === 0) return allEdges ?? [];
    return (allEdges ?? []).filter((edge) => edgeTypes.includes(edge.type));
  }, [allEdges, edgeTypes]);

  // Memoized (not just a plain ternary) now that the hierarchy layer below
  // depends on these in its own useMemo calls — `entities ?? []` would
  // otherwise hand out a fresh empty array every render while loading.
  const visibleNodes = useMemo(
    () => (viewMode === "all" ? (entities ?? []) : focusedNodes),
    [viewMode, entities, focusedNodes],
  );
  const visibleEdges = useMemo(
    () => (viewMode === "all" ? allModeEdges : (subgraph?.edges ?? [])),
    [viewMode, allModeEdges, subgraph],
  );
  const isLargeWorld =
    viewMode === "all" && (entities?.length ?? 0) > LARGE_WORLD_NOTICE_THRESHOLD;

  const selectedEdge = visibleEdges.find((e) => e.id === selectedEdgeId) ?? null;

  // Presentation layer on top of the current All/Focused result above, not a
  // replacement for it: built from `visibleNodes`/`visibleEdges` exactly as
  // they stand (so Focused mode's BFS/depth cutoff is respected — collapse
  // never silently reaches past it), then handed to GraphCanvas as the
  // node/edge arrays it actually renders. See lib/hierarchy.ts for why this
  // reuses buildForest/buildHierarchy instead of a second grouping model.
  const hierarchyIndex = useMemo(
    () => buildHierarchy(visibleEdges, hierarchyConfig),
    [visibleEdges, hierarchyConfig],
  );
  const hierarchyParentIds = useMemo(() => {
    const ids = new Set<string>();
    for (const node of visibleNodes) {
      if (hierarchyIndex.childrenOf.has(node.id)) ids.add(node.id);
    }
    return ids;
  }, [visibleNodes, hierarchyIndex]);
  const hierarchyVisibility = useMemo(
    () => computeHierarchyVisibility(visibleNodes, hierarchyIndex, graphCollapse.collapsedIds),
    [visibleNodes, hierarchyIndex, graphCollapse.collapsedIds],
  );
  const canvasNodes = useMemo(
    () => visibleNodes.filter((entity) => hierarchyVisibility.visibleIds.has(entity.id)),
    [visibleNodes, hierarchyVisibility],
  );
  const canvasEdges = useMemo(
    () => filterVisibleEdges(visibleEdges, hierarchyVisibility.visibleIds),
    [visibleEdges, hierarchyVisibility],
  );

  return (
    // On the graph page, "go to entity" re-points the detail panel instead of
    // leaving the canvas — wikilink chips inside the panel use this too.
    <EntityNavigationContext.Provider value={setSelectedEntityId}>
      <div className="graph-view-page">
      <div className="graph-canvas-area">
        {viewMode === "focused" && !rootId && !isEmptyWorld && (
          <p className="graph-empty-state">{t("graph.pickRoot")}</p>
        )}
        {isEmptyWorld && (
          <p className="graph-empty-state">{t("graph.emptyWorld")}</p>
        )}
        {viewMode === "focused" && rootId && isLoading && (
          <p className="graph-empty-state">{t("common.loading")}</p>
        )}
        {viewMode === "all" && entities === undefined && (
          <p className="graph-empty-state">{t("common.loading")}</p>
        )}
        {isLargeWorld && !largeWorldNoticeDismissed && (
          <div className="graph-large-world-notice">
            <span>{t("graph.largeWorldNotice")}</span>
            <button
              type="button"
              className="icon-button"
              aria-label={t("graph.closeAssistant")}
              onClick={() => setLargeWorldNoticeDismissed(true)}
            >
              <Icon name="x" size={14} />
            </button>
          </div>
        )}

        {/* Assistant toggle and drawer share one flex column, starting right
            at the top of the canvas — the view/filter controls used to sit
            above them here too, which visually collided with the sidebar's
            project switcher popover opening in the same corner. */}
        <div className="graph-overlay-left">
          {!assistantVisible && (
            <button
              type="button"
              className="assistant-drawer-toggle"
              title={t("graph.openAssistant")}
              aria-label={t("graph.openAssistant")}
              onClick={() => setAssistantOpen(true)}
            >
              <Icon name="sparkles" size={16} />
            </button>
          )}
          {assistantVisible && (
            <aside className="assistant-drawer">
              <div className="assistant-drawer-header">
                <span>{t("graph.openAssistant")}</span>
                <button
                  type="button"
                  className="icon-button assistant-drawer-close"
                  aria-label={t("graph.closeAssistant")}
                  onClick={() => setAssistantOpen(false)}
                >
                  <Icon name="x" />
                </button>
              </div>
              <AssistantPanel
                projectId={projectId!}
                onCommitted={(entityIds) => {
                  // Focus the freshly generated web on the canvas.
                  if (entityIds.length > 0) changeRoot(entityIds[0]);
                }}
              />
            </aside>
          )}
        </div>
        {(viewMode === "all" ? entities !== undefined : rootId && subgraph) && (
          <GraphCanvas
            projectId={projectId!}
            nodes={canvasNodes}
            edges={canvasEdges}
            rootId={rootId}
            depth={depth}
            viewMode={viewMode}
            selectedEntityId={selectedEntityId}
            focusRequest={focusRequest}
            actionRequest={actionRequest}
            locked={locked}
            gridEnabled={gridEnabled}
            hierarchyParentIds={hierarchyParentIds}
            hierarchyCollapsedIds={graphCollapse.collapsedIds}
            hierarchyHiddenCounts={hierarchyVisibility.hiddenDescendantCount}
            onToggleHierarchyCollapse={graphCollapse.toggle}
            onNodeSelect={setSelectedEntityId}
            onNodeSetRoot={changeRoot}
            onConnectNodes={(sourceId, targetId) => setPendingConnection({ sourceId, targetId })}
            onEdgeSelect={setSelectedEdgeId}
            onPaneClick={() => setSelectedEntityId(null)}
          />
        )}

        {/* Filters and the create button live together at the bottom-center
            of the canvas — "change what's shown" and "add something new"
            read as one related cluster of canvas-level actions. */}
        <div className="graph-dock-wrap">
          <GraphControls
            entities={entities ?? []}
            rootId={rootId}
            depth={depth}
            edgeTypes={edgeTypes}
            availableEdgeTypes={availableEdgeTypes}
            viewMode={viewMode}
            locked={locked}
            gridEnabled={gridEnabled}
            onRootChange={changeRoot}
            onDepthChange={setDepth}
            onEdgeTypesChange={setEdgeTypes}
            onViewModeChange={setViewMode}
            onAction={dispatchGraphAction}
            onCenterView={centerView}
            onLockedChange={setLocked}
            onGridEnabledChange={setGridEnabled}
            hasHierarchyBranches={hierarchyParentIds.size > 0}
            onCollapseAllHierarchy={() => graphCollapse.collapseAll(hierarchyParentIds)}
            onExpandAllHierarchy={graphCollapse.expandAll}
          />

          {(viewMode === "all" || rootId) && (
            <GraphCreateEntityButton
              projectId={projectId!}
              onCreated={(entity) => {
                setTempEntities((prev) => [...prev, entity]);
                setSelectedEntityId(entity.id);
              }}
            />
          )}
        </div>

        <EntityDetailPanel
          key={selectedEntityId}
          projectId={projectId!}
          entityId={selectedEntityId}
          rootId={rootId}
          onClose={() => setSelectedEntityId(null)}
          onNavigate={setSelectedEntityId}
          onDeleted={(id) => {
            setTempEntities((prev) => prev.filter((e) => e.id !== id));
            setSelectedEntityId(null);
          }}
          onSetRoot={changeRoot}
          onFocusCamera={focusCameraOn}
        />
      </div>

      {pendingConnection && (
        <div className="popover-backdrop" onClick={() => setPendingConnection(null)}>
          <div onClick={(e) => e.stopPropagation()}>
            <EdgeQuickForm
              projectId={projectId!}
              sourceId={pendingConnection.sourceId}
              targetId={pendingConnection.targetId}
              onDone={(edge) => {
                setPendingConnection(null);
                // Once an edge is created, the connected entity will appear in
                // the subgraph via BFS — drop it from local temp state.
                if (edge) {
                  const connectedId =
                    edge.source_entity_id === pendingConnection.sourceId
                      ? edge.target_entity_id
                      : edge.source_entity_id;
                  setTempEntities((prev) => prev.filter((e) => e.id !== connectedId));
                }
              }}
            />
          </div>
        </div>
      )}

      {selectedEdge && (
        <div className="popover-backdrop" onClick={() => setSelectedEdgeId(null)}>
          <div onClick={(e) => e.stopPropagation()}>
            <EdgeEditPopover
              projectId={projectId!}
              edge={selectedEdge}
              onDone={() => setSelectedEdgeId(null)}
            />
          </div>
        </div>
      )}
      </div>
    </EntityNavigationContext.Provider>
  );
}
