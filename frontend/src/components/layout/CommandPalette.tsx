import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useEntities } from "../../hooks/useEntities";
import { useProjects } from "../../hooks/useProjects";
import { Icon } from "../ui/Icon";

interface Props {
  projectId: string | undefined;
  open: boolean;
  onClose: () => void;
}

interface Result {
  id: string;
  label: string;
  hint: string;
  to: string;
}

/** How many rows a search can produce before it stops being a shortcut and
 * starts being a list you have to read. */
const MAX_RESULTS = 8;

/** Jump straight to an entity or a project by name.
 *
 * Scope is what the client already holds: the open project's entities and
 * every project. That covers the case the rail was missing — "I know the
 * name, I just want to be there" — without a search endpoint the backend
 * doesn't have yet. */
export function CommandPalette({ projectId, open, onClose }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: projects } = useProjects();
  const { data: entities } = useEntities(projectId);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      inputRef.current?.focus();
    }
  }, [open]);

  const results = useMemo<Result[]>(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];
    const found: Result[] = [];
    for (const entity of entities ?? []) {
      if (entity.title.toLowerCase().includes(needle)) {
        found.push({
          id: `entity-${entity.id}`,
          label: entity.title,
          hint: entity.type,
          to: `/projects/${entity.project_id}/entities/${entity.id}`,
        });
      }
    }
    for (const project of projects ?? []) {
      if (project.name.toLowerCase().includes(needle)) {
        found.push({
          id: `project-${project.id}`,
          label: project.name,
          hint: t("palette.projectHint"),
          to: `/projects/${project.id}/entities`,
        });
      }
    }
    return found.slice(0, MAX_RESULTS);
  }, [query, entities, projects, t]);

  if (!open) return null;

  function go(result: Result) {
    onClose();
    navigate(result.to);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      onClose();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (results.length ? (c + 1) % results.length : 0));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => (results.length ? (c - 1 + results.length) % results.length : 0));
    }
    if (e.key === "Enter" && results[cursor]) {
      go(results[cursor]);
    }
  }

  return (
    <div className="palette-backdrop" onMouseDown={onClose} role="presentation">
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label={t("palette.title")}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="palette-input-row">
          <Icon name="search" size={16} />
          <input
            ref={inputRef}
            value={query}
            placeholder={
              projectId ? t("palette.placeholder") : t("palette.placeholderNoProject")
            }
            onChange={(e) => {
              setQuery(e.target.value);
              setCursor(0);
            }}
          />
          {/* Esc still closes; the hint is replaced by something clickable,
              which is the only route for anyone reaching for the mouse. */}
          <button
            type="button"
            className="palette-close"
            onClick={onClose}
            title={t("common.close")}
            aria-label={t("common.close")}
          >
            <Icon name="x" size={15} />
          </button>
        </div>

        {query.trim() !== "" && results.length === 0 && (
          <p className="palette-empty">{t("palette.nothing", { query: query.trim() })}</p>
        )}

        {results.length > 0 && (
          <ul className="palette-results">
            {results.map((result, index) => (
              <li key={result.id}>
                <button
                  type="button"
                  className={index === cursor ? "active" : ""}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => go(result)}
                >
                  <span className="palette-label">{result.label}</span>
                  <span className="palette-hint">{result.hint}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {query.trim() === "" && <p className="palette-empty">{t("palette.hint")}</p>}
      </div>
    </div>
  );
}
