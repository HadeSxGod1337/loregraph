import { useTranslation } from "react-i18next";

import type { UpdateMode } from "../../api/types";
import { useSetUpdatePreferences, useUpdateStatus } from "../../hooks/useUpdates";
import { Markdown } from "../ui/Markdown";

const MODES: UpdateMode[] = ["ask", "auto", "never"];
const MODE_LABEL: Record<UpdateMode, string> = {
  ask: "updates.modeAsk",
  auto: "updates.modeAuto",
  never: "updates.modeNever",
};

/** Update controls, shown as a settings section (they used to be buried in
 * the appearance popover, which is not where anyone looks for a version).
 * Global on purpose: the launcher checks the remote for the whole app, not
 * one project. The backend only reads what the launcher wrote, so there's no
 * "check now" — the mode and the skip list are what the user controls. */
export function UpdatesSection() {
  const { t } = useTranslation();
  const { data: status } = useUpdateStatus();
  const setPreferences = useSetUpdatePreferences();

  if (!status) return null;

  const { preferences, latest_version: latest } = status;

  function setMode(mode: UpdateMode) {
    setPreferences.mutate({ ...preferences, mode });
  }

  function toggleSkip(version: string) {
    const skipped = preferences.skipped_versions.includes(version)
      ? preferences.skipped_versions.filter((v) => v !== version)
      : [...preferences.skipped_versions, version];
    setPreferences.mutate({ ...preferences, skipped_versions: skipped });
  }

  const isSkipped =
    latest !== null && preferences.skipped_versions.includes(latest);

  return (
    <div className="updates-section">
      <p className="updates-version">
        {t("updates.currentVersion", { version: status.current_version })}
      </p>

      {!status.git_available && (
        <p className="updates-note">{t("updates.unavailable")}</p>
      )}

      {status.update_available && latest && (
        <div className="updates-available">
          <strong>{t("updates.available", { version: latest })}</strong>
          {status.worktree_dirty ? (
            <p className="updates-note">{t("updates.dirty")}</p>
          ) : (
            <p className="updates-note">{t("updates.restartHint")}</p>
          )}
          {status.changelog && (
            <details className="updates-changelog">
              <summary>{t("updates.whatsNew")}</summary>
              <Markdown>{status.changelog}</Markdown>
            </details>
          )}
          <button
            type="button"
            className="updates-skip-btn"
            onClick={() => toggleSkip(latest)}
          >
            {t("updates.skip", { version: latest })}
          </button>
        </div>
      )}

      {status.git_available && !status.update_available && (
        <p className="updates-note">
          {isSkipped && latest
            ? t("updates.skipped", { version: latest })
            : t("updates.upToDate")}
          {isSkipped && latest && (
            <>
              {" "}
              <button
                type="button"
                className="updates-link-btn"
                onClick={() => toggleSkip(latest)}
              >
                {t("updates.unskip")}
              </button>
            </>
          )}
        </p>
      )}

      <div className="settings-inline-row">
        <span className="settings-inline-label">{t("updates.mode")}</span>
        <div className="theme-mode-toggle">
          {MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              className={preferences.mode === mode ? "active" : ""}
              onClick={() => setMode(mode)}
            >
              {t(MODE_LABEL[mode])}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
