import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../api/client";
import type { Edge } from "../api/types";
import { AssistantPanel } from "../components/assistant/AssistantPanel";
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
  const { projectId } = useParams<{ projectId: string }>();
  const { data: entities } = useEntities(projectId!);
  const [rootId, setRootId] = useState("");
  const [depth, setDepth] = useState(2);
  const [edgeTypesInput, setEdgeTypesInput] = useState("");
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

  const edgeTypes = useMemo(
    () =>
      edgeTypesInput
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length > 0),
    [edgeTypesInput],
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
        <GraphControls
          entities={entities ?? []}
          rootId={rootId}
          depth={depth}
          edgeTypesInput={edgeTypesInput}
          onRootChange={changeRoot}
          onDepthChange={setDepth}
          onEdgeTypesInputChange={setEdgeTypesInput}
        />

        {!rootId && !isEmptyWorld && (
          <p className="graph-empty-state">Pick a root entity to view its neighborhood.</p>
        )}
        {isEmptyWorld && (
          <p className="graph-empty-state">
            Your world is empty — describe it in the AI panel and review the
            generated starting lore.
          </p>
        )}
        {rootId && isLoading && <p className="graph-empty-state">Loading...</p>}

        {!assistantVisible && (
          <button
            type="button"
            className="assistant-drawer-toggle"
            onClick={() => setAssistantOpen(true)}
          >
            ✨ AI Assistant
          </button>
        )}
        {assistantVisible && (
          <aside className="assistant-drawer">
            <div className="assistant-drawer-header">
              <span>✨ AI Assistant</span>
              <button
                type="button"
                className="assistant-drawer-close"
                aria-label="Close assistant"
                onClick={() => setAssistantOpen(false)}
              >
                ✕
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
