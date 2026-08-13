import { useTranslation } from "react-i18next";

import type { ThemeMode } from "../../theme/presets";
import { useTheme } from "../../theme/ThemeContext";
import { Icon, type IconName } from "../ui/Icon";

const MODES: { mode: ThemeMode; icon: IconName }[] = [
  { mode: "light", icon: "sun" },
  { mode: "dark", icon: "moon" },
  { mode: "system", icon: "monitor" },
];

/** The one preference frequent enough to earn space in the rail.
 *
 * Everything else that used to share a popover with it — accent, language,
 * updates — is a decision you make once, and now lives in Settings where it
 * can be explained properly.
 *
 * Collapsed, three targets don't fit in a 62 px rail, so it becomes one
 * button that cycles: light → dark → system. */
export function ThemeToggle({ collapsed }: { collapsed: boolean }) {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();

  const currentIndex = MODES.findIndex((item) => item.mode === theme);
  const current = MODES[currentIndex === -1 ? 0 : currentIndex];

  if (collapsed) {
    const next = MODES[(currentIndex + 1) % MODES.length];
    return (
      <button
        type="button"
        className="sidebar-theme-cycle"
        title={t("sidebar.themeNext", { mode: t(`theme.${next.mode}`) })}
        aria-label={t("sidebar.themeNext", { mode: t(`theme.${next.mode}`) })}
        onClick={() => setTheme(next.mode)}
      >
        <Icon name={current.icon} size={15} />
      </button>
    );
  }

  return (
    <div className="sidebar-theme-toggle" role="group" aria-label={t("sidebar.theme")}>
      {MODES.map(({ mode, icon }) => (
        <button
          key={mode}
          type="button"
          className={theme === mode ? "active" : ""}
          aria-pressed={theme === mode}
          title={t(`theme.${mode}`)}
          aria-label={t(`theme.${mode}`)}
          onClick={() => setTheme(mode)}
        >
          <Icon name={icon} size={14} />
        </button>
      ))}
    </div>
  );
}
