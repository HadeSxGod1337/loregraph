import { useTranslation } from "react-i18next";

import { SUPPORTED_LANGUAGES, type SupportedLanguage } from "../../i18n";

const LANGUAGE_LABELS: Record<SupportedLanguage, string> = {
  en: "EN",
  ru: "RU",
};

/** Mirrors ThemePicker's segmented-button pattern. Persistence is handled by
 * i18next-browser-languagedetector (localStorage), not here. */
export function LanguagePicker() {
  const { i18n } = useTranslation();
  const current = i18n.resolvedLanguage ?? "en";

  return (
    <div className="theme-mode-toggle">
      {SUPPORTED_LANGUAGES.map((lng) => (
        <button
          key={lng}
          type="button"
          className={current === lng ? "active" : ""}
          onClick={() => void i18n.changeLanguage(lng)}
        >
          {LANGUAGE_LABELS[lng]}
        </button>
      ))}
    </div>
  );
}
