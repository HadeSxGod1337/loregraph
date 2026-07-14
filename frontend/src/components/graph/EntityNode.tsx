import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { CSSProperties } from "react";

import { typeColor, typeSoftBackground } from "../../lib/typeColor";

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
  const color = typeColor(entityType);
  return (
    <div
      className={`entity-node${isRoot ? " entity-node-root" : ""}${isSelected ? " entity-node-selected" : ""}`}
      style={{ "--type-color": color } as CSSProperties}
    >
      <Handle type="target" position={Position.Top} id="target-top" isConnectable />
      <Handle type="target" position={Position.Left} id="target-left" isConnectable />
      <Handle type="target" position={Position.Right} id="target-right" isConnectable />
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
      <Handle type="source" position={Position.Bottom} id="source-bottom" isConnectable />
      <Handle type="source" position={Position.Left} id="source-left" isConnectable />
      <Handle type="source" position={Position.Right} id="source-right" isConnectable />
    </div>
  );
}
