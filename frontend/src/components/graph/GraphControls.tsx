import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Entity } from "../../api/types";
import { Icon } from "../ui/Icon";

const DEPTH_OPTIONS = [1, 2, 3] as const;
const MAX_COMBOBOX_OPTIONS = 50;

interface GraphControlsProps {
  entities: Entity[];
  rootId: string;
  depth: number;
  edgeTypes: string[];
  availableEdgeTypes: string[];
  onRootChange: (rootId: string) => void;
  onDepthChange: (depth: number) => void;
  onEdgeTypesChange: (types: string[]) => void;
}

export function GraphControls({
  entities,
  rootId,
  depth,
  edgeTypes,
  availableEdgeTypes,
  onRootChange,
  onDepthChange,
  onEdgeTypesChange,
}: GraphControlsProps) {
  const { t } = useTranslation();
  return (
    <div className="graph-controls">
      <label>
        {t("graph.rootEntity")}
        <RootCombobox entities={entities} rootId={rootId} onRootChange={onRootChange} />
      </label>

      <div className="graph-controls-row">
        <label>
          {t("graph.depth")}
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
        </label>

        {availableEdgeTypes.length > 0 && (
          <label style={{ flex: 1, minWidth: 0 }}>
            {t("graph.edgeTypesLabel")}
            <EdgeTypeMultiselect
              available={availableEdgeTypes}
              selected={edgeTypes}
              onChange={onEdgeTypesChange}
            />
          </label>
        )}
      </div>
    </div>
  );
}

/** Searchable entity picker — a native select over hundreds of entities is
 * unusable; this filters as you type. */
function RootCombobox({
  entities,
  rootId,
  onRootChange,
}: {
  entities: Entity[];
  rootId: string;
  onRootChange: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  const selectedTitle = entities.find((e) => e.id === rootId)?.title ?? "";

  const options = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matched = q
      ? entities.filter((e) => e.title.toLowerCase().includes(q))
      : entities;
    return matched.slice(0, MAX_COMBOBOX_OPTIONS);
  }, [entities, query]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="combobox" ref={rootRef}>
      <input
        role="combobox"
        aria-expanded={open}
        placeholder={t("graph.rootSearchPlaceholder")}
        value={open ? query : selectedTitle}
        onFocus={() => {
          setQuery("");
          setOpen(true);
        }}
        onChange={(e) => setQuery(e.target.value)}
      />
      {open && (
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
      )}
    </div>
  );
}

/** Checkbox dropdown over the edge types that actually exist in this world —
 * replaces the old comma-separated text input. Empty selection = all types. */
function EdgeTypeMultiselect({
  available,
  selected,
  onChange,
}: {
  available: string[];
  selected: string[];
  onChange: (types: string[]) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function toggle(type: string) {
    onChange(
      selected.includes(type)
        ? selected.filter((item) => item !== type)
        : [...selected, type],
    );
  }

  return (
    <div className="multiselect" ref={rootRef}>
      <button
        type="button"
        className="multiselect-toggle"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {selected.length === 0
          ? t("graph.edgeTypesAll")
          : t("graph.edgeTypesSelected", { count: selected.length })}
        <Icon name="chevron-down" size={14} />
      </button>
      {open && (
        <div className="multiselect-list" role="listbox">
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
      )}
    </div>
  );
}
