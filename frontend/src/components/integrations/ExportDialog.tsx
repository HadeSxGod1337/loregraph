import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Connection, ExportPreviewItem, ExportResult } from "../../api/types";
import { useExportPreview, useRunExport } from "../../hooks/useConnections";
import { translateApiError } from "../../i18n/eventText";
import { Icon } from "../ui/Icon";
import { useToast } from "../ui/Toast";

type Phase = "preview" | "confirm" | "running" | "done";

const ACTION_LABELS: Record<string, () => string> = {};

export function ExportDialog({
  projectId,
  connection,
  onClose,
}: {
  projectId: string;
  connection: Connection;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const preview = useExportPreview(projectId);
  const runExport = useRunExport(projectId);

  const [phase, setPhase] = useState<Phase>("preview");
  const [items, setItems] = useState<ExportPreviewItem[]>([]);
  const [result, setResult] = useState<ExportResult | null>(null);

  // Fetch preview on mount.
  useEffect(() => {
    preview.mutate(
      { connectionId: connection.id },
      {
        onSuccess: (data) => {
          setItems(data.items);
          setPhase("confirm");
        },
        onError: () => setPhase("confirm"),
      },
    );
    // Only on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleExport() {
    setPhase("running");
    runExport.mutate(
      { connectionId: connection.id },
      {
        onSuccess: (data) => {
          setResult(data);
          setPhase("done");
          toast(
            t("integrations.exportDone", {
              created: data.created,
              updated: data.updated,
              skipped: data.skipped,
            }),
          );
        },
        onError: (err) => {
          toast(translateApiError(err, t));
          setPhase("confirm");
        },
      },
    );
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t("integrations.exportTitle")}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{t("integrations.exportTitle")}</h2>

        {phase === "preview" && (
          <p className="field-hint">{t("common.loading")}</p>
        )}

        {phase === "confirm" && (
          <>
            {items.length === 0 ? (
              <p className="field-hint">{t("integrations.exportNothing")}</p>
            ) : (
              <table className="export-preview-table">
                <thead>
                  <tr>
                    <th>{t("integrations.previewEntity")}</th>
                    <th>{t("integrations.previewAction")}</th>
                    <th>{t("integrations.previewTarget")}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.entity_id}>
                      <td>{item.title}</td>
                      <td>
                        <span className={`export-action-${item.action}`}>
                          {t(`integrations.action.${item.action}`)}
                        </span>
                      </td>
                      <td className="export-target-cell">{item.target}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}

        {phase === "running" && (
          <p className="field-hint">{t("integrations.exportRunning")}</p>
        )}

        {phase === "done" && result && (
          <div className="export-result-summary">
            <p>
              {t("integrations.exportDone", {
                created: result.created,
                updated: result.updated,
                skipped: result.skipped,
              })}
            </p>
            {result.errors.length > 0 && (
              <ul className="export-error-list">
                {result.errors.map((err, i) => (
                  <li key={i} className="error-text">
                    {err.ref}: {err.detail}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="dialog-actions">
          <button type="button" className="button-ghost" onClick={onClose}>
            {phase === "done" ? t("common.close") : t("common.cancel")}
          </button>
          {phase === "confirm" && items.length > 0 && (
            <button
              type="button"
              className="button-primary"
              disabled={runExport.isPending}
              onClick={handleExport}
            >
              {t("integrations.exportConfirm")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
