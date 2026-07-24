import { useState } from "react";
import { useTranslation } from "react-i18next";

const REPO_URL = "https://github.com/HadeSxGod1337/loregraph";

/** A slim, dismissible ribbon shown only in the GitHub Pages demo build. States
 * plainly that edits are ephemeral and the assistant is scripted — and that the
 * real app is BYOK (you pay your own LLM provider). Fixed to the bottom so it
 * never disturbs the sticky sidebar / full-bleed graph layout. Rendered from
 * App, gated on import.meta.env.VITE_DEMO, so it never appears self-hosted. */
export function DemoBanner() {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return (
    <div className="demo-banner" role="note">
      <span className="demo-banner-badge">{t("demo.badge")}</span>
      <span className="demo-banner-text">{t("demo.banner")}</span>
      <a className="demo-banner-link" href={REPO_URL} target="_blank" rel="noreferrer">
        {t("demo.source")}
      </a>
      <button
        type="button"
        className="demo-banner-close"
        aria-label={t("common.close")}
        onClick={() => setDismissed(true)}
      >
        ×
      </button>
    </div>
  );
}
