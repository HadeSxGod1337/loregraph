import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { DEFAULT_PRESET, DEFAULT_THEME_MODE, type ThemeMode } from "./presets";

interface ThemeContextValue {
  theme: ThemeMode;
  preset: string;
  setTheme: (theme: ThemeMode) => void;
  setPreset: (preset: string) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function resolveTheme(theme: ThemeMode): "light" | "dark" {
  if (theme !== "system") return theme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(
    () => (localStorage.getItem("theme") as ThemeMode | null) ?? DEFAULT_THEME_MODE,
  );
  const [preset, setPresetState] = useState<string>(
    () => localStorage.getItem("preset") ?? DEFAULT_PRESET,
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", resolveTheme(theme));
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => document.documentElement.setAttribute("data-theme", resolveTheme(theme));
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  useEffect(() => {
    document.documentElement.setAttribute("data-preset", preset);
  }, [preset]);

  const setTheme = useCallback((next: ThemeMode) => {
    localStorage.setItem("theme", next);
    setThemeState(next);
  }, []);

  const setPreset = useCallback((next: string) => {
    localStorage.setItem("preset", next);
    setPresetState(next);
  }, []);

  const value = useMemo(
    () => ({ theme, preset, setTheme, setPreset }),
    [theme, preset, setTheme, setPreset],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
