import { PRESETS } from "../../theme/presets";
import { useTheme } from "../../theme/ThemeContext";

const MODES = [
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
  { id: "system", label: "System" },
] as const;

export function ThemePicker() {
  const { theme, preset, setTheme, setPreset } = useTheme();

  return (
    <div className="theme-picker">
      <div className="theme-mode-toggle">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            className={theme === mode.id ? "active" : ""}
            onClick={() => setTheme(mode.id)}
          >
            {mode.label}
          </button>
        ))}
      </div>
      <select value={preset} onChange={(e) => setPreset(e.target.value)}>
        {PRESETS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>
    </div>
  );
}
