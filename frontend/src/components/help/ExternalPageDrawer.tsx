import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { useEmbedLoadStatus } from "../../hooks/useEmbedLoadStatus";
import { Icon } from "../ui/Icon";

interface ExternalPageDrawerProps {
  title: string;
  url: string;
  /** The feedback form needs to submit; the read-only hub doesn't — sandbox
   * stays as narrow as the specific page actually requires. */
  allowForms?: boolean;
  onClose: () => void;
  minEmbedMs?: number;
  maxWaitMs?: number;
}

/** A public page shown in-app without leaving Loregraph, for providers we
 * don't control and never proxy through the backend. Most third-party sites
 * (Notion's public pages included) send a frame-ancestors CSP that refuses
 * anyone else's origin, and browsers give no catchable error for that — only
 * a console message — so whether the embed actually rendered is inferred
 * from how quickly the frame settles (see useEmbedLoadStatus). Either way
 * "open in a new tab" stays one click away. */
export function ExternalPageDrawer({
  title,
  url,
  allowForms = false,
  onClose,
  minEmbedMs,
  maxWaitMs,
}: ExternalPageDrawerProps) {
  const { t } = useTranslation();
  const { status, onIframeLoad } = useEmbedLoadStatus(url, { minEmbedMs, maxWaitMs });

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
            <iframe
              className={
                "embed-overlay-iframe" +
                (status === "loading" ? " embed-overlay-iframe-hidden" : "")
              }
              src={url}
              title={title}
              sandbox={sandbox}
              referrerPolicy="no-referrer"
              onLoad={onIframeLoad}
            />
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
