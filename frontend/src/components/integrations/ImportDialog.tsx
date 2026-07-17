import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Connection, ImportResult } from "../../api/types";
import { useRunImport } from "../../hooks/useConnections";
import { translateApiError } from "../../i18n/eventText";
import { useToast } from "../ui/Toast";

type Phase = "input" | "running" | "done";

/** Regex for LongStoryShort share URLs — 24-hex character id. */
const LSS_URL_RE = /longstoryshort\.app\/characters\/digital\/([0-9a-f]{24})/;

export function ImportDialog({
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
  const runImport = useRunImport(projectId);

  const [phase, setPhase] = useState<Phase>("input");
  const [shareUrl, setShareUrl] = useState("");
  const [rawJson, setRawJson] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);

  const isLss = connection.connector_type === "longstoryshort";

  function handleImport() {
    setPhase("running");

    const payload: Record<string, unknown> = {};
    if (isLss) {
      if (shareUrl.trim()) {
        payload.share_url = shareUrl.trim();
      } else if (rawJson.trim()) {
        try {
          payload.raw_json = JSON.parse(rawJson);
        } catch {
          toast(t("integrations.importInvalidJson"));
          setPhase("input");
          return;
        }
      }
    }

    runImport.mutate(
      { connectionId: connection.id, request: { payload } },
      {
        onSuccess: (data) => {
          setResult(data);
          setPhase("done");
          toast(
            t("integrations.importDone", {
              created: data.created,
              updated: data.updated,
              skipped: data.skipped,
            }),
          );
        },
        onError: (err) => {
          toast(translateApiError(err, t));
          setPhase("input");
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
        aria-label={t("integrations.importTitle")}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{t("integrations.importTitle")}</h2>

        {phase === "input" && (
          <>
            {isLss ? (
              <>
                <label>
                  {t("integrations.importShareUrl")}
                  <input
                    type="url"
                    value={shareUrl}
                    onChange={(e) => setShareUrl(e.target.value)}
                    placeholder="https://longstoryshort.app/characters/digital/..."
                  />
                </label>
                <div className="import-or-divider">
                  {t("integrations.importOr")}
                </div>
                <label>
                  {t("integrations.importRawJson")}
                  <textarea
                    rows={5}
                    value={rawJson}
                    onChange={(e) => setRawJson(e.target.value)}
                    placeholder='{"name": "...", "level": 3, ...}'
                  />
                </label>
              </>
            ) : (
              <p className="field-hint">{t("integrations.importHint")}</p>
            )}
          </>
        )}

        {phase === "running" && (
          <p className="field-hint">{t("integrations.importRunning")}</p>
        )}

        {phase === "done" && result && (
          <div className="export-result-summary">
            <p>
              {t("integrations.importDone", {
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
          {phase === "input" && (
            <button
              type="button"
              className="button-primary"
              disabled={
                runImport.isPending ||
                (isLss && !shareUrl.trim() && !rawJson.trim())
              }
              onClick={handleImport}
            >
              {t("integrations.importConfirm")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
