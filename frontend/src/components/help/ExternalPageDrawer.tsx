import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { useEmbedLoadStatus } from "../../hooks/useEmbedLoadStatus";
import { Icon } from "../ui/Icon";

interface ExternalPageDrawerProps {
  title: string;
  /** Canonical page — used for "open in a new tab" links only. */
  url: string;
  /** Provider's dedicated embed route for the same page, loaded in the
   * iframe. Kept separate from `url` because the two can behave
   * differently: Notion's canonical page URL refuses third-party framing
   * outright, its `/ebd/` route doesn't. */
  embedUrl: string;
  /** The feedback form needs to submit; the read-only hub doesn't — sandbox
   * stays as narrow as the specific page actually requires. */
  allowForms?: boolean;
  onClose: () => void;
  maxWaitMs?: number;
}

/** A public page shown in-app without leaving Loregraph, for providers we
 * don't control and never proxy through the backend. "Open in a new tab"
 * stays one click away regardless of whether the embed loads — both in the
 * header and, once embedded, as a small link under the frame, since a
 * third party's embed behavior isn't something to fully trust blind. */
export function ExternalPageDrawer({
  title,
  url,
  embedUrl,
  allowForms = false,
  onClose,
  maxWaitMs,
}: ExternalPageDrawerProps) {
  const { t } = useTranslation();
  const { status, onIframeLoad } = useEmbedLoadStatus(embedUrl, { maxWaitMs });

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const sandbox = allowForms
    ? "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms"
    : "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox";

  return (
    <div className="embed-overlay-backdrop" onClick={onClose}>
      <div
        className="embed-overlay"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="embed-overlay-head">
          <h2>{title}</h2>
          <div className="embed-overlay-actions">
            <a
              className="button-ghost button-sm"
              href={url}
              target="_blank"
              rel="noreferrer noopener"
            >
              <Icon name="external-link" size={13} />
              {t("common.openInNewTab")}
            </a>
            <button
              type="button"
              className="embed-overlay-close"
              aria-label={t("common.close")}
              onClick={onClose}
            >
              <Icon name="x" size={16} />
            </button>
          </div>
        </div>

        <div className="embed-overlay-body">
          {status === "loading" && (
            <div className="embed-overlay-loading">
              <span className="spinner" aria-hidden="true" />
              {t("common.loading")}
            </div>
          )}

          {status !== "blocked" && (
            <div className="embed-overlay-frame-wrap">
              <iframe
                className={
                  "embed-overlay-iframe" +
                  (status === "loading" ? " embed-overlay-iframe-hidden" : "")
                }
                src={embedUrl}
                title={title}
                sandbox={sandbox}
                referrerPolicy="no-referrer"
                onLoad={onIframeLoad}
              />
              {status === "embedded" && (
                <p className="embed-overlay-hint">
                  {t("help.support.troubleLoading")}{" "}
                  <a href={url} target="_blank" rel="noreferrer noopener">
                    {t("common.openInNewTab")}
                  </a>
                </p>
              )}
            </div>
          )}

          {status === "blocked" && (
            <div className="embed-overlay-fallback">
              <Icon name="external-link" size={26} />
              <p>{t("help.support.blockedMessage")}</p>
              <a
                className="button-primary"
                href={url}
                target="_blank"
                rel="noreferrer noopener"
              >
                {t("common.openInNewTab")}
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
