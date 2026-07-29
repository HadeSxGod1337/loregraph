import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Connection, ImportResult } from "../../api/types";
import { useRunImport } from "../../hooks/useConnections";
import { translateApiError } from "../../i18n/eventText";
import { Icon } from "../ui/Icon";
import { useToast } from "../ui/Toast";
import { LSS_CONNECTOR_TYPE } from "./connectorMeta";

type Phase = "input" | "running" | "done";

interface PickedFile {
  name: string;
  content: string;
}

/** Import from a connection. For LongStoryShort — the one connector whose
 * import needs input from the DM — this is the character-sheet importer:
 * drop in the files a party exported from the site, all of them at once.
 *
 * Sheets used to come in strictly one at a time, through a form that asked
 * for a share URL first even though LSS publishes no endpoint we may read
 * (see the connector's module docstring) — so the path that actually works,
 * the exported file, was the third choice on the dialog. It is now the
 * first, and the share link is the fallback it really is. */
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
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [phase, setPhase] = useState<Phase>("input");
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [shareUrl, setShareUrl] = useState("");
  const [rawJson, setRawJson] = useState("");
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  const isLss = connection.connector_type === LSS_CONNECTOR_TYPE;

  async function addFiles(picked: FileList | null) {
    if (!picked || picked.length === 0) return;
    const read = await Promise.all(
      [...picked].map(
        async (file): Promise<PickedFile> => ({
          name: file.name,
          content: await file.text(),
        }),
      ),
    );
    // Re-dropping a file replaces its earlier content rather than importing
    // the same character twice in one run.
    setFiles((prev) => [
      ...prev.filter((file) => !read.some((next) => next.name === file.name)),
      ...read,
    ]);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    void addFiles(e.dataTransfer.files);
  }

  function handleImport() {
    const payload: Record<string, unknown> = {};
    if (isLss) {
      if (files.length > 0) {
        payload.documents = files.map((file) => ({
          name: file.name,
          content: file.content,
        }));
      } else if (shareUrl.trim()) {
        payload.share_url = shareUrl.trim();
      } else if (rawJson.trim()) {
        // Validate JSON syntax client-side, but send the raw string — the
        // backend's LssImportPayload.raw_json expects str, not object.
        try {
          JSON.parse(rawJson);
        } catch {
          toast(t("integrations.importInvalidJson"));
          return;
        }
        payload.raw_json = rawJson.trim();
      }
    }

    setPhase("running");
    runImport.mutate(
      { connectionId: connection.id, request: { payload } },
      {
        onSuccess: (data) => {
          setResult(data);
          setPhase("done");
        },
        onError: (err) => {
          toast(translateApiError(err, t));
          setPhase("input");
        },
      },
    );
  }

  const hasInput = isLss
    ? files.length > 0 || !!(shareUrl.trim() || rawJson.trim())
    : true;

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className="dialog import-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={isLss ? t("integrations.importSheetsTitle") : t("integrations.importTitle")}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{isLss ? t("integrations.importSheetsTitle") : t("integrations.importTitle")}</h2>

        {phase === "input" &&
          (isLss ? (
            <>
              <p className="field-hint">{t("integrations.importSheetsHint")}</p>

              {/* Outside the drop zone on purpose: a hidden input *inside* a
                  clickable parent turns the programmatic .click() into an
                  event that bubbles straight back to the parent's handler. */}
              <input
                ref={fileInputRef}
                type="file"
                accept=".json,application/json"
                multiple
                onChange={(e) => {
                  void addFiles(e.target.files);
                  e.target.value = "";
                }}
                style={{ display: "none" }}
              />
              <button
                type="button"
                className={"import-dropzone" + (dragging ? " dragging" : "")}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <Icon name="upload" size={18} />
                <span className="import-dropzone-title">
                  {t("integrations.importDropTitle")}
                </span>
                <span className="field-hint">{t("integrations.importDropHint")}</span>
              </button>

              {files.length > 0 && (
                <ul className="import-file-list">
                  {files.map((file) => (
                    <li key={file.name}>
                      <Icon name="paperclip" size={13} />
                      <span className="import-file-name">{file.name}</span>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={t("common.delete")}
                        onClick={() =>
                          setFiles((prev) => prev.filter((f) => f.name !== file.name))
                        }
                      >
                        <Icon name="x" size={13} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <details className="import-advanced">
                <summary>{t("integrations.importOtherWays")}</summary>
                <label>
                  {t("integrations.importShareUrl")}
                  <input
                    type="url"
                    value={shareUrl}
                    onChange={(e) => setShareUrl(e.target.value)}
                    placeholder="https://longstoryshort.app/characters/digital/..."
                  />
                </label>
                <p className="field-hint">{t("integrations.importShareUrlHint")}</p>
                <label>
                  {t("integrations.importRawJson")}
                  <textarea
                    rows={4}
                    value={rawJson}
                    onChange={(e) => setRawJson(e.target.value)}
                    placeholder='{"name": "...", "level": 3, ...}'
                  />
                </label>
              </details>
            </>
          ) : (
            <p className="field-hint">{t("integrations.importHint")}</p>
          ))}

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
            {result.items.length > 0 && (
              <ul className="import-result-list">
                {result.items.map((item) => (
                  <li key={item.entity_id}>
                    <span className="import-file-name">{item.title}</span>
                    <span className="import-result-action">
                      {t(`integrations.itemAction.${item.action}`)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {isLss && result.items.length > 0 && (
              <p className="field-hint">{t("integrations.importSheetsDoneHint")}</p>
            )}
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
              disabled={runImport.isPending || !hasInput}
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
