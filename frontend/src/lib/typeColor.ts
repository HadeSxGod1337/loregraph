/*
  Deterministic entity-type → color mapping, shared by list badges, filter
  chips, avatar placeholders and graph cards, so a type is recognizable by
  hue before its label is read.

  All hues are mid-saturation so they read on both light and dark themes;
  translucent backgrounds are derived via color-mix at the call site.
*/

const TYPE_PALETTE = [
  "#5b8def", // blue
  "#4cae7e", // green
  "#c77f3a", // ochre
  "#a06fd6", // violet
  "#d6608a", // rose
  "#3aa7b8", // cyan
  "#96a13d", // olive
  "#c06c5c", // clay
] as const;

/* The default types get stable colors regardless of hashing, so worlds built
 * from the standard vocabulary always look the same. */
const FIXED_TYPE_COLORS: Record<string, string> = {
  npc: "#5b8def",
  location: "#4cae7e",
  faction: "#c77f3a",
  item: "#a06fd6",
  session: "#3aa7b8",
};

export function typeColor(type: string): string {
  const key = type.trim().toLowerCase();
  const fixed = FIXED_TYPE_COLORS[key];
  if (fixed) return fixed;
  let hash = 0;
  for (const char of key) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return TYPE_PALETTE[hash % TYPE_PALETTE.length];
}

/** Translucent tint of the type color, for badge/avatar backgrounds. */
export function typeSoftBackground(type: string): string {
  return `color-mix(in srgb, ${typeColor(type)} 15%, transparent)`;
}
