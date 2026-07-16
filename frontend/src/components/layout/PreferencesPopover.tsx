import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useDismiss } from "../../hooks/useDismiss";
import { SUPPORTED_LANGUAGES, type SupportedLanguage } from "../../i18n";
import { PRESETS, type ThemeMode } from "../../theme/presets";
import { useTheme } from "../../theme/ThemeContext";
import { Icon } from "../ui/Icon";

const MODES: ThemeMode[] = ["light", "dark", "system"];
const LANGUAGE_LABELS: Record<SupportedLanguage, string> = { en: "EN", ru: "RU" };

/** Merges the old ThemePicker + LanguagePicker + the bare preset `<select>`
 * into one popover — three disconnected NavBar controls become one place. */
export function PreferencesPopover({ collapsed }: { collapsed: boolean }) {
  const { t, i18n } = useTranslation();
  const { theme, preset, setTheme, setPreset } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  useDismiss(open, rootRef, () => setOpen(false));

  const currentLanguage = (i18n.resolvedLanguage ?? "en") as SupportedLanguage;

  return (
    <div className="sidebar-prefs-wrap" ref={rootRef}>
      <button
        type="button"
        className="sidebar-prefs-btn"
        aria-haspopup="dialog"
        aria-expanded={open}
        title={collapsed ? t("sidebar.appearance") : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="appearance" size={16} />
        {!collapsed && <span>{t("sidebar.appearance")}</span>}
      </button>

      {open && (
        <div className="sidebar-prefs-popover" role="dialog" aria-label={t("sidebar.appearance")}>
          <h3>{t("sidebar.appearance")}</h3>

          <div className="sidebar-pref-row">
            <span className="sidebar-pref-label">{t("sidebar.theme")}</span>
            <div className="theme-mode-toggle">
              {MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={theme === mode ? "active" : ""}
                  onClick={() => setTheme(mode)}
                >
                  {t(`theme.${mode}`)}
                </button>
              ))}
            </div>
          </div>

          <div className="sidebar-pref-row">
            <span className="sidebar-pref-label">{t("sidebar.accent")}</span>
            <div className="sidebar-swatches">
              {PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  data-preset={p.id}
                  className={"sidebar-swatch" + (preset === p.id ? " active" : "")}
                  title={p.label}
                  aria-label={p.label}
                  aria-pressed={preset === p.id}
                  onClick={() => setPreset(p.id)}
                >
                  {preset === p.id && <Icon name="check" size={11} />}
                </button>
              ))}
            </div>
          </div>

          <div className="sidebar-pref-row">
            <span className="sidebar-pref-label">{t("sidebar.language")}</span>
            <div className="theme-mode-toggle">
              {SUPPORTED_LANGUAGES.map((lng) => (
                <button
                  key={lng}
                  type="button"
                  className={currentLanguage === lng ? "active" : ""}
                  onClick={() => void i18n.changeLanguage(lng)}
                >
                  {LANGUAGE_LABELS[lng]}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
