import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Entity } from "../../api/types";
import { useDismiss } from "../../hooks/useDismiss";
import { HelpIcon } from "../ui/Tooltip";
import { Icon } from "../ui/Icon";

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
  onRootChange: (rootId: string) => void;
  onDepthChange: (depth: number) => void;
  onEdgeTypesChange: (types: string[]) => void;
  onViewModeChange: (mode: GraphViewMode) => void;
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
  onRootChange,
  onDepthChange,
  onEdgeTypesChange,
  onViewModeChange,
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
                  <span className="graph-filter-label">
                    {t("graph.depth")}
                    <HelpIcon content={t("tooltips.depth")} side="right" />
                  </span>
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
        <label key={type}>
          <input
            type="checkbox"
            checked={selected.includes(type)}
            onChange={() => toggle(type)}
          />
          {type}
        </label>
      ))}
    </div>
  );
}
