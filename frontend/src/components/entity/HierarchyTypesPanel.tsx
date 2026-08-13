import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useAllEdges } from "../../hooks/useEdgesForEntity";
import {
  useHierarchyConfig,
  type HierarchyRole,
} from "../../hooks/useHierarchyConfig";

const ROLES: HierarchyRole[] = ["none", "forward", "inverse"];

/** Which relationship types the entity list turns into folders.
 *
 * The rows are the types this project actually uses (plus anything already
 * configured), because the vocabulary is written by the DM and the agent, not
 * fixed by the app — a list of invented types to choose from would be a list
 * of types nobody wrote. */
export function HierarchyTypesPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { data: edges } = useAllEdges(projectId);
  const { config, roleOf, setRole, reset, isDefault } = useHierarchyConfig(projectId);

  const types = useMemo(() => {
    const used = new Map<string, number>();
    for (const edge of edges ?? []) {
      used.set(edge.type, (used.get(edge.type) ?? 0) + 1);
    }
    for (const type of [...config.forward, ...config.inverse]) {
      if (!used.has(type)) used.set(type, 0);
    }
    // Types the project leans on first; the rest alphabetically.
    return [...used.entries()].sort(
      (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
    );
  }, [config, edges]);

  return (
    <section className="settings-card">
      <div className="settings-card-head">
        <h2>{t("projectSettings.groupingHeading")}</h2>
        <p className="field-hint">{t("projectSettings.groupingHint")}</p>
      </div>

      {types.length === 0 ? (
        <p className="field-hint">{t("projectSettings.groupingNoEdges")}</p>
      ) : (
        <ul className="hierarchy-type-list">
          {types.map(([type, count]) => (
            <li key={type} className="hierarchy-type-row">
              <span className="hierarchy-type-name">
                <code>{type}</code>
                <span className="type-chip-count">{count}</span>
              </span>
              <div
                className="segmented"
                role="group"
                aria-label={t("projectSettings.groupingRoleFor", { type })}
              >
                {ROLES.map((role) => (
                  <button
                    key={role}
                    type="button"
                    className={roleOf(type) === role ? "active" : undefined}
                    aria-pressed={roleOf(type) === role}
                    onClick={() => setRole(type, role)}
                  >
                    {t(`projectSettings.groupingRole_${role}`)}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="settings-save-row">
        <button type="button" onClick={reset} disabled={isDefault}>
          {t("projectSettings.groupingReset")}
        </button>
      </div>
    </section>
  );
}
