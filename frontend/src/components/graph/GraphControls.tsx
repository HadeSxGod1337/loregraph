import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  return (
    <div className="graph-controls">
      <label>
        {t("graph.rootEntity")}
        <select value={rootId} onChange={(e) => onRootChange(e.target.value)}>
          <option value="">{t("graph.selectPlaceholder")}</option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title} ({e.type})
            </option>
          ))}
        </select>
      </label>

      <label>
        {t("graph.depth")}
        <input
          type="number"
          min={0}
          max={10}
          value={depth}
          onChange={(e) => onDepthChange(Number(e.target.value))}
        />
      </label>

      <label>
        {t("graph.edgeTypesLabel")}
        <input
          placeholder={t("graph.edgeTypesPlaceholder")}
          value={edgeTypesInput}
          onChange={(e) => onEdgeTypesInputChange(e.target.value)}
        />
      </label>
    </div>
  );
}
