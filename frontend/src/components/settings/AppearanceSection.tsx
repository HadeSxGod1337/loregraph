import { useTranslation } from "react-i18next";

import { SUPPORTED_LANGUAGES, type SupportedLanguage } from "../../i18n";
import { PRESETS, type ThemeMode } from "../../theme/presets";
import { useTheme } from "../../theme/ThemeContext";
import { Icon, type IconName } from "../ui/Icon";

const MODES: { mode: ThemeMode; icon: IconName }[] = [
  { mode: "light", icon: "sun" },
  { mode: "dark", icon: "moon" },
  { mode: "system", icon: "monitor" },
];

const LANGUAGE_LABELS: Record<SupportedLanguage, string> = {
  en: "English",
  ru: "Русский",
};

/** Theme, accent and language — the three things that used to share one
 * popover with app updates.
 *
 * Here each gets room for the thing the popover could not show: what the
 * choice actually looks like. The preset tiles are the presets themselves,
 * painted with their own palettes, not swatches of an accent color. */
export function AppearanceSection() {
  const { t, i18n } = useTranslation();
  const { theme, preset, setTheme, setPreset } = useTheme();
  const currentLanguage = (i18n.resolvedLanguage ?? "en") as SupportedLanguage;

  return (
    <section className="settings-card">
      <div className="settings-card-head">
        <h2>{t("appearance.themeHeading")}</h2>
        <p className="field-hint">{t("appearance.themeHint")}</p>
      </div>

      <div className="appearance-modes">
        {MODES.map(({ mode, icon }) => (
          <button
            key={mode}
            type="button"
            className={"appearance-mode" + (theme === mode ? " active" : "")}
            aria-pressed={theme === mode}
            onClick={() => setTheme(mode)}
          >
            <span className={"appearance-mode-preview mode-" + mode} aria-hidden="true" />
            <span className="appearance-mode-label">
              <Icon name={icon} size={14} />
              {t(`theme.${mode}`)}
            </span>
          </button>
        ))}
      </div>

      <div className="settings-editable-divider" />

      <div className="settings-card-head">
        <h2>{t("appearance.accentHeading")}</h2>
        <p className="field-hint">{t("appearance.accentHint")}</p>
      </div>

      <div className="appearance-presets">
        {PRESETS.map((item) => (
          <button
            key={item.id}
            type="button"
            data-preset={item.id}
            className={"appearance-preset" + (preset === item.id ? " active" : "")}
            aria-pressed={preset === item.id}
            onClick={() => setPreset(item.id)}
          >
            <span className="appearance-preset-bar" aria-hidden="true">
              <i className="tone-bg" />
              <i className="tone-surface" />
              <i className="tone-accent" />
            </span>
            <span className="appearance-preset-name">
              {item.label}
              {preset === item.id && <Icon name="check" size={13} />}
            </span>
          </button>
        ))}
      </div>

      <div className="settings-editable-divider" />

      <div className="settings-card-head">
        <h2>{t("appearance.languageHeading")}</h2>
        <p className="field-hint">{t("appearance.languageHint")}</p>
      </div>

      <div className="appearance-langs">
        {SUPPORTED_LANGUAGES.map((lng) => (
          <button
            key={lng}
            type="button"
            className={currentLanguage === lng ? "active" : ""}
            aria-pressed={currentLanguage === lng}
            onClick={() => void i18n.changeLanguage(lng)}
          >
            {LANGUAGE_LABELS[lng]}
          </button>
        ))}
      </div>
    </section>
  );
}
