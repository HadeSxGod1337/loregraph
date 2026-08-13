import { useTranslation } from "react-i18next";

import type { AppSettings } from "../../api/appSettings";
import { useReindexStatus, useStartReindex } from "../../hooks/useAppSettings";
import { translateApiError } from "../../i18n/eventText";

interface Props {
  settings: AppSettings;
}

/** Progress of the rebuild that has to follow an embedding-model change.
 *
 * It starts by itself when the model changes — leaving it to the user would
 * mean the assistant silently retrieves nothing until they press a button
 * they have no reason to look for — so this panel mostly explains what is
 * already happening, and offers a manual run for a repair. */
export function ReindexPanel({ settings }: Props) {
  const { t } = useTranslation();
  const start = useStartReindex();
  // The status embedded in /settings is a snapshot; polling takes over while
  // a job runs and stops the moment it doesn't.
  const { data: polled } = useReindexStatus(settings.reindex.state === "running");
  const status = polled ?? settings.reindex;
  const running = status.state === "running";

  return (
    <div className="reindex-row">
      <div className="reindex-copy">
        <p className="reindex-label">{t("appSettings.reindexHeading")}</p>
        <p className="field-hint">
          {settings.embeddings_enabled
            ? t("appSettings.reindexHint", { model: settings.embedding_model_id ?? "" })
            : t("appSettings.reindexDisabledHint")}
        </p>

        {running && (
          <>
            <p className="field-hint">
              {t("appSettings.reindexProgress", {
                done: status.done_projects,
                total: status.total_projects,
                current: status.current_project ?? "",
              })}
            </p>
            {/* Documents are the slow half: one large rulebook can outlast
                every entity in the installation, so it gets its own line
                rather than looking like a stall. */}
            {status.total_sources > 0 && (
              <p className="field-hint">
                {t("appSettings.reindexSourceProgress", {
                  done: status.sources_indexed,
                  total: status.total_sources,
                  current: status.current_source ?? "",
                })}
              </p>
            )}
          </>
        )}
        {status.state === "done" && (
          <p className="field-hint">
            {t("appSettings.reindexDone", {
              entities: status.entities_indexed,
              sources: status.sources_indexed,
            })}
          </p>
        )}
        {status.state === "error" && (
          <p className="error-text">
            {t("appSettings.reindexFailed", { error: status.error ?? "" })}
          </p>
        )}
      </div>

      <div className="settings-save-row">
        <button
          type="button"
          disabled={running || start.isPending || !settings.embeddings_enabled}
          onClick={() => start.mutate()}
        >
          {(running || start.isPending) && <span className="spinner" aria-hidden="true" />}
          {running ? t("appSettings.reindexing") : t("appSettings.reindexButton")}
        </button>
        {start.isError && (
          <span className="error-text">{translateApiError(start.error, t)}</span>
        )}
      </div>
    </div>
  );
}
