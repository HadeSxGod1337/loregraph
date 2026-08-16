import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Entity } from "../../api/types";
import { useDismiss } from "../../hooks/useDismiss";
import { Checkbox } from "../ui/Checkbox";
import { Icon } from "../ui/Icon";
import { KebabMenu } from "../ui/KebabMenu";
import type { GraphActionType } from "./GraphCanvas";

const DEPTH_OPTIONS = [1, 2, 3] as const;
const MAX_COMBOBOX_OPTIONS = 50;

export type GraphViewMode = "focused" | "all";

interface GraphControlsProps {
  entities: Entity[];
  rootId: string;
  depth: number;
  edgeTypes: string[];
  availableEdgeTypes: string[];
  viewMode: GraphViewMode;
  /** See GraphCanvasProps — freezes dragging/connecting/selecting. */
  locked: boolean;
  onRootChange: (rootId: string) => void;
  onDepthChange: (depth: number) => void;
  onEdgeTypesChange: (types: string[]) => void;
  onViewModeChange: (mode: GraphViewMode) => void;
  /** Fire-once camera/layout commands — see GraphActionRequest. */
  onAction: (type: GraphActionType) => void;
  /** Centers the camera on whatever's currently selected, falling back to
   * the root/active entity — reuses the same focusRequest plumbing as the
   * detail panel's own "focus camera" button (see GraphViewPage). */
  onCenterView: () => void;
  onLockedChange: (locked: boolean) => void;
}

/** Horizontal dock anchored at the bottom of the canvas, next to the create
 * button — previously a tall card pinned top-left, which visually collided
 * with the sidebar's project switcher popover opening in the same corner. */
export function GraphControls({
  entities,
  rootId,
  depth,
  edgeTypes,
  availableEdgeTypes,
  viewMode,
  locked,
  onRootChange,
  onDepthChange,
  onEdgeTypesChange,
  onViewModeChange,
  onAction,
  onCenterView,
  onLockedChange,
}: GraphControlsProps) {
  const { t } = useTranslation();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersRef = useRef<HTMLDivElement>(null);
  useDismiss(filtersOpen, filtersRef, () => setFiltersOpen(false));

  const hasFilterableSettings = viewMode === "focused" || availableEdgeTypes.length > 0;
  // Depth has a sensible default the moment you enter Focused mode, so it
  // doesn't count as "filtered" on its own — edge-type selection does.
  const hasActiveFilters = edgeTypes.length > 0;

  return (
    <div className="graph-dock">
      <div
        className="segmented graph-view-mode-toggle"
        role="group"
        aria-label={t("graph.viewMode")}
      >
        <button
          type="button"
          className={viewMode === "all" ? "active" : ""}
          onClick={() => onViewModeChange("all")}
        >
          {t("graph.viewModeAll")}
        </button>
        <button
          type="button"
          className={viewMode === "focused" ? "active" : ""}
          onClick={() => onViewModeChange("focused")}
        >
          {t("graph.viewModeFocused")}
        </button>
      </div>

      <div className="graph-dock-divider" />

      <RootCombobox
        entities={entities}
        rootId={rootId}
        onRootChange={onRootChange}
        label={t(viewMode === "all" ? "graph.activeEntity" : "graph.rootEntity")}
      />

      {hasFilterableSettings && (
        <div className="graph-dock-trigger" ref={filtersRef}>
          <button
            type="button"
            className="graph-dock-trigger-btn"
            aria-haspopup="dialog"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen((v) => !v)}
          >
            <Icon name="filter" size={13} />
            <span className="graph-dock-value">{t("graph.filters")}</span>
            {hasActiveFilters && <span className="graph-filter-badge" aria-hidden="true" />}
          </button>

          {filtersOpen && (
            <div className="graph-dock-popover graph-filters-popover">
              {viewMode === "focused" && (
                <div className="graph-filter-block">
                  <span className="graph-filter-label">{t("graph.depth")}</span>
                  <div className="segmented" role="group" aria-label={t("graph.depth")}>
                    {DEPTH_OPTIONS.map((option) => (
                      <button
                        key={option}
                        type="button"
                        className={depth === option ? "active" : ""}
                        onClick={() => onDepthChange(option)}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {availableEdgeTypes.length > 0 && (
                <div className="graph-filter-block">
                  <span className="graph-filter-label">{t("graph.edgeTypesLabel")}</span>
                  <EdgeTypeChecklist
                    available={availableEdgeTypes}
                    selected={edgeTypes}
                    onChange={onEdgeTypesChange}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="graph-dock-divider" />

      <div className="segmented graph-zoom-cluster" role="group" aria-label={t("graph.zoomGroup")}>
        <button type="button" title={t("graph.zoomOut")} aria-label={t("graph.zoomOut")} onClick={() => onAction("zoomOut")}>
          <Icon name="zoom-out" size={14} />
        </button>
        <button type="button" title={t("graph.fitView")} aria-label={t("graph.fitView")} onClick={() => onAction("fitView")}>
          <Icon name="maximize" size={14} />
        </button>
        <button type="button" title={t("graph.zoomIn")} aria-label={t("graph.zoomIn")} onClick={() => onAction("zoomIn")}>
          <Icon name="zoom-in" size={14} />
        </button>
      </div>

      <button
        type="button"
        className="graph-dock-icon-btn"
        title={t("graph.centerView")}
        aria-label={t("graph.centerView")}
        onClick={onCenterView}
      >
        <Icon name="expand" size={14} />
      </button>

      <KebabMenu
        label={t("graph.moreActions")}
        placement="up"
        items={[
          { label: t("graph.resetLayout"), onClick: () => onAction("resetLayout") },
          {
            label: locked ? t("graph.unlockPositions") : t("graph.lockPositions"),
            onClick: () => onLockedChange(!locked),
          },
        ]}
      />
    </div>
  );
}

/** Searchable entity picker — a native select over hundreds of entities is
 * unusable; this filters as you type. Packaged as a trigger + popover (not
 * an always-visible input) to fit the dock, and opens upward since the dock
 * sits at the bottom of the canvas. */
function RootCombobox({
  entities,
  rootId,
  onRootChange,
  label,
}: {
  entities: Entity[];
  rootId: string;
  onRootChange: (id: string) => void;
  label: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  useDismiss(open, rootRef, () => setOpen(false));

  const selectedTitle = entities.find((e) => e.id === rootId)?.title ?? "";

  const options = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matched = q
      ? entities.filter((e) => e.title.toLowerCase().includes(q))
      : entities;
    return matched.slice(0, MAX_COMBOBOX_OPTIONS);
  }, [entities, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      inputRef.current?.focus();
    }
  }, [open]);

  return (
    <div className="graph-dock-trigger combobox" ref={rootRef}>
      <button
        type="button"
        className="graph-dock-trigger-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        title={label}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="target" size={13} />
        <span className="graph-dock-value">{selectedTitle || t("graph.selectPlaceholder")}</span>
        <Icon name="chevron-down" size={12} />
      </button>

      {open && (
        <div className="graph-dock-popover combobox-popover">
          <input
            ref={inputRef}
            className="combobox-search"
            placeholder={t("graph.rootSearchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <ul className="combobox-list">
            {options.map((entity) => (
              <li key={entity.id}>
                <button
                  type="button"
                  onClick={() => {
                    onRootChange(entity.id);
                    setOpen(false);
                  }}
                >
                  <span>{entity.title}</span>
                  <span className="combobox-option-type">{entity.type}</span>
                </button>
              </li>
            ))}
            {options.length === 0 && (
              <li className="combobox-empty">{t("entityLink.noMatches")}</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Plain checkbox list — lives inside the Filters popover, so it doesn't
 * need its own trigger/popover the way the old EdgeTypeMultiselect did. */
function EdgeTypeChecklist({
  available,
  selected,
  onChange,
}: {
  available: string[];
  selected: string[];
  onChange: (types: string[]) => void;
}) {
  function toggle(type: string) {
    onChange(
      selected.includes(type)
        ? selected.filter((item) => item !== type)
        : [...selected, type],
    );
  }

  return (
    <div className="graph-filter-checks">
      {available.map((type) => (
        <Checkbox
          key={type}
          label={type}
          checked={selected.includes(type)}
          onChange={() => toggle(type)}
        />
      ))}
    </div>
  );
}
