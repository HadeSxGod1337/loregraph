import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

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
    <div className="graph-view-page">
      <div className="graph-canvas-area">
        <GraphControls
          entities={entities ?? []}
          rootId={rootId}
          depth={depth}
          edgeTypesInput={edgeTypesInput}
          onRootChange={setRootId}
          onDepthChange={setDepth}
          onEdgeTypesInputChange={setEdgeTypesInput}
        />

        {!rootId && (
          <p className="graph-empty-state">Pick a root entity to view its neighborhood.</p>
        )}
        {rootId && isLoading && <p className="graph-empty-state">Loading...</p>}
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
  );
}
