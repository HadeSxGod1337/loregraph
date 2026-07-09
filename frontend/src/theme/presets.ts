export interface ThemePreset {
  id: string;
  label: string;
}

export const PRESETS: ThemePreset[] = [
  { id: "teal", label: "Teal" },
  { id: "blue", label: "Blue" },
  { id: "green", label: "Green" },
  { id: "violet", label: "Violet" },
  { id: "amber", label: "Amber" },
  { id: "slate", label: "Slate" },
  { id: "noir", label: "Noir" },
];

export const DEFAULT_PRESET = "teal";

export type ThemeMode = "light" | "dark" | "system";
export const DEFAULT_THEME_MODE: ThemeMode = "system";
