import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { apiClient } from "../api/client";
import type { Edge } from "../api/types";
import { AssistantPanel } from "../components/assistant/AssistantPanel";
import { Icon } from "../components/ui/Icon";
import { EntityNavigationContext } from "../components/EntityNavigationContext";
import { EdgeEditPopover } from "../components/graph/EdgeEditPopover";
import { EdgeQuickForm } from "../components/graph/EdgeQuickForm";
import { EntityDetailPanel } from "../components/graph/EntityDetailPanel";
import { GraphCanvas } from "../components/graph/GraphCanvas";
import { GraphControls } from "../components/graph/GraphControls";
import { useEntities } from "../hooks/useEntities";
import { useSubgraph } from "../hooks/useSubgraph";

interface PendingConnection {
  sourceId: string;
  targetId: string;
}

export function GraphViewPage() {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();
  const { data: entities } = useEntities(projectId!);
  const [rootId, setRootId] = useState("");
  const [depth, setDepth] = useState(2);
  const [edgeTypes, setEdgeTypes] = useState<string[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [pendingConnection, setPendingConnection] = useState<PendingConnection | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
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

  const availableEdgeTypes = useMemo(
    () => [...new Set((allEdges ?? []).map((edge) => edge.type))].sort(),
    [allEdges],
  );

  const { data: subgraph, isLoading } = useSubgraph(
    projectId!,
    rootId || undefined,
    depth,
    edgeTypes.length > 0 ? edgeTypes : undefined,
  );

  const selectedEdge = subgraph?.edges.find((e) => e.id === selectedEdgeId) ?? null;

  return (
    // On the graph page, "go to entity" re-points the detail panel instead of
    // leaving the canvas — wikilink chips inside the panel use this too.
    <EntityNavigationContext.Provider value={setSelectedEntityId}>
      <div className="graph-view-page">
      <div className="graph-canvas-area">
        {!rootId && !isEmptyWorld && (
          <p className="graph-empty-state">{t("graph.pickRoot")}</p>
        )}
        {isEmptyWorld && (
          <p className="graph-empty-state">{t("graph.emptyWorld")}</p>
        )}
        {rootId && isLoading && <p className="graph-empty-state">{t("common.loading")}</p>}

        {/* Controls, assistant toggle and drawer share one flex column, so
            each element starts right below the previous one regardless of
            their heights. */}
        <div className="graph-overlay-left">
          <GraphControls
            entities={entities ?? []}
            rootId={rootId}
            depth={depth}
            edgeTypes={edgeTypes}
            availableEdgeTypes={availableEdgeTypes}
            onRootChange={changeRoot}
            onDepthChange={setDepth}
            onEdgeTypesChange={setEdgeTypes}
          />

          {!assistantVisible && (
            <button
              type="button"
              className="assistant-drawer-toggle"
              onClick={() => setAssistantOpen(true)}
            >
              <Icon name="sparkles" size={15} />
              {t("graph.openAssistant")}
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
        {rootId && subgraph && (
          <GraphCanvas
            nodes={subgraph.nodes}
            edges={subgraph.edges}
            rootId={rootId}
            selectedEntityId={selectedEntityId}
            onNodeSelect={setSelectedEntityId}
            onConnectNodes={(sourceId, targetId) => setPendingConnection({ sourceId, targetId })}
            onEdgeSelect={setSelectedEdgeId}
            onPaneClick={() => setSelectedEntityId(null)}
          />
        )}

        <EntityDetailPanel
          key={selectedEntityId}
          projectId={projectId!}
          entityId={selectedEntityId}
          onClose={() => setSelectedEntityId(null)}
          onNavigate={setSelectedEntityId}
        />
      </div>

      {pendingConnection && (
        <div className="popover-backdrop" onClick={() => setPendingConnection(null)}>
          <div onClick={(e) => e.stopPropagation()}>
            <EdgeQuickForm
              projectId={projectId!}
              sourceId={pendingConnection.sourceId}
              targetId={pendingConnection.targetId}
              onDone={() => setPendingConnection(null)}
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
