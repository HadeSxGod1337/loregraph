import type { Entity } from "../../api/types";

interface GraphControlsProps {
  entities: Entity[];
  rootId: string;
  depth: number;
  edgeTypesInput: string;
  onRootChange: (rootId: string) => void;
  onDepthChange: (depth: number) => void;
  onEdgeTypesInputChange: (value: string) => void;
}

export function GraphControls({
  entities,
  rootId,
  depth,
  edgeTypesInput,
  onRootChange,
  onDepthChange,
  onEdgeTypesInputChange,
}: GraphControlsProps) {
  return (
    <div className="graph-controls">
      <label>
        Root entity
        <select value={rootId} onChange={(e) => onRootChange(e.target.value)}>
          <option value="">— select —</option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title} ({e.type})
            </option>
          ))}
        </select>
      </label>

      <label>
        Depth
        <input
          type="number"
          min={0}
          max={10}
          value={depth}
          onChange={(e) => onDepthChange(Number(e.target.value))}
        />
      </label>

      <label>
        Edge types (comma-separated, empty = all)
        <input
          placeholder="ally_of, family_of"
          value={edgeTypesInput}
          onChange={(e) => onEdgeTypesInputChange(e.target.value)}
        />
      </label>
    </div>
  );
}
