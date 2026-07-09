import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface PreviewField {
  key: string;
  value: string;
}

export interface EntityNodeData extends Record<string, unknown> {
  label: string;
  entityType: string;
  isRoot: boolean;
  isSelected: boolean;
  iconUrl?: string | null;
  previewFields: PreviewField[];
}

export function EntityNode({ data }: NodeProps) {
  const { label, entityType, isRoot, isSelected, iconUrl, previewFields } =
    data as EntityNodeData;
  return (
    <div
      className={`entity-node${isRoot ? " entity-node-root" : ""}${isSelected ? " entity-node-selected" : ""}`}
    >
      <Handle type="target" position={Position.Top} />
      <div className="entity-node-info">
        <span className="entity-type-badge">{entityType}</span>
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
      <div className="entity-node-icon-slot">
        {iconUrl ? (
          <img className="entity-node-icon" src={iconUrl} alt="" />
        ) : (
          <span className="entity-node-icon-placeholder" aria-hidden="true" />
        )}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
