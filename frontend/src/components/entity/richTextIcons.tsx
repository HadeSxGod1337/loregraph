import type { ReactNode } from "react";

/** Toolbar glyphs. 16x16, stroke-based, `currentColor` — so a button's active
 * state only has to change `color`, never swap an asset. */
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const icons = {
  bold: (
    <Icon>
      <path d="M4.5 8h4a2.5 2.5 0 0 0 0-5h-4v10h4.7a2.5 2.5 0 0 0 0-5" />
    </Icon>
  ),
  italic: (
    <Icon>
      <path d="M10 3H6.5M9.5 13H6M9 3l-2 10" />
    </Icon>
  ),
  underline: (
    <Icon>
      <path d="M4.5 2.5v5a3.5 3.5 0 0 0 7 0v-5M3.5 13.5h9" />
    </Icon>
  ),
  strike: (
    <Icon>
      <path d="M2.5 8h11M11.5 4.2C11 3.1 9.7 2.5 8 2.5 6 2.5 4.7 3.5 4.7 5c0 1 .6 1.7 1.8 2.2M4.5 11.4c.6 1.4 1.9 2.1 3.6 2.1 2.1 0 3.4-1 3.4-2.6 0-.9-.4-1.6-1.2-2.1" />
    </Icon>
  ),
  code: (
    <Icon>
      <path d="M5.5 4.5 2 8l3.5 3.5M10.5 4.5 14 8l-3.5 3.5" />
    </Icon>
  ),
  paragraph: (
    <Icon>
      <path d="M8 3v10M11 3v10M11 3H7a2 2 0 0 0 0 4h1" />
    </Icon>
  ),
  quote: (
    <Icon>
      <path d="M3 4h3v4H4a1 1 0 0 1-1-1zM3 8c0 2 .8 3.2 2.5 3.7M9.5 4h3v4h-2a1 1 0 0 1-1-1zM9.5 8c0 2 .8 3.2 2.5 3.7" />
    </Icon>
  ),
  codeBlock: (
    <Icon>
      <rect x="1.8" y="2.8" width="12.4" height="10.4" rx="1.6" />
      <path d="M6 6.2 4.4 8 6 9.8M10 6.2 11.6 8 10 9.8" />
    </Icon>
  ),
  bulletList: (
    <Icon>
      <path d="M6 4h8M6 8h8M6 12h8" />
      <circle cx="3" cy="4" r=".9" fill="currentColor" stroke="none" />
      <circle cx="3" cy="8" r=".9" fill="currentColor" stroke="none" />
      <circle cx="3" cy="12" r=".9" fill="currentColor" stroke="none" />
    </Icon>
  ),
  orderedList: (
    <Icon>
      <path d="M6.5 4h7.5M6.5 8h7.5M6.5 12h7.5M2 3.2l1-.7V6M1.7 9.3c0-1.3 2.3-1.1 2.3.1 0 .8-2.3 1.6-2.3 3h2.6" />
    </Icon>
  ),
  taskList: (
    <Icon>
      <path d="M8 4h6M8 11.5h6" />
      <rect x="1.5" y="1.8" width="4.4" height="4.4" rx="1" />
      <path d="M2.6 4.1 3.6 5l1.7-1.9" />
      <rect x="1.5" y="9.3" width="4.4" height="4.4" rx="1" />
    </Icon>
  ),
  alignLeft: (
    <Icon>
      <path d="M2 3.5h12M2 6.8h8M2 10.1h12M2 13.4h8" />
    </Icon>
  ),
  alignCenter: (
    <Icon>
      <path d="M2 3.5h12M4 6.8h8M2 10.1h12M4 13.4h8" />
    </Icon>
  ),
  alignRight: (
    <Icon>
      <path d="M2 3.5h12M6 6.8h8M2 10.1h12M6 13.4h8" />
    </Icon>
  ),
  alignJustify: (
    <Icon>
      <path d="M2 3.5h12M2 6.8h12M2 10.1h12M2 13.4h12" />
    </Icon>
  ),
  indent: (
    <Icon>
      <path d="M6.5 4h7.5M6.5 8h7.5M6.5 12h7.5M1.8 6 4 8l-2.2 2" />
    </Icon>
  ),
  outdent: (
    <Icon>
      <path d="M6.5 4h7.5M6.5 8h7.5M6.5 12h7.5M4 6 1.8 8 4 10" />
    </Icon>
  ),
  link: (
    <Icon>
      <path d="M6.6 9.4a2.6 2.6 0 0 0 3.7 0l2.2-2.2a2.6 2.6 0 0 0-3.7-3.7l-.9.9" />
      <path d="M9.4 6.6a2.6 2.6 0 0 0-3.7 0L3.5 8.8a2.6 2.6 0 0 0 3.7 3.7l.9-.9" />
    </Icon>
  ),
  unlink: (
    <Icon>
      <path d="M9.6 6.4a2.6 2.6 0 0 1 .7 2.4M6.4 9.6a2.6 2.6 0 0 1 .5-2.7" />
      <path d="M10.2 4.9l.6-.6a2.6 2.6 0 0 1 3.7 3.7l-1.4 1.4M5.8 11.1l-.6.6a2.6 2.6 0 0 1-3.7-3.7l1.4-1.4M2 2l12 12" />
    </Icon>
  ),
  image: (
    <Icon>
      <rect x="1.8" y="2.8" width="12.4" height="10.4" rx="1.6" />
      <circle cx="5.6" cy="6.2" r="1.1" />
      <path d="M2.2 11.6 5.5 8.6l2.4 2.1 2.4-2.5 3.5 3.4" />
    </Icon>
  ),
  table: (
    <Icon>
      <rect x="1.8" y="2.8" width="12.4" height="10.4" rx="1.4" />
      <path d="M1.8 6.4h12.4M1.8 9.8h12.4M6.2 2.8v10.4" />
    </Icon>
  ),
  hr: (
    <Icon>
      <path d="M2 8h12M4 4h8M4 12h8" opacity=".55" />
      <path d="M2 8h12" />
    </Icon>
  ),
  color: (
    <Icon>
      <path d="M3.5 12.5h9" strokeWidth="2.4" />
      <path d="M4.4 9.6 8 2.2l3.6 7.4M5.7 7.6h4.6" />
    </Icon>
  ),
  highlight: (
    <Icon>
      <path d="M3 13.2h10" strokeWidth="2.4" />
      <path d="M5.4 10.4 3.9 8.9l5-5 1.5 1.5zM9 3.4l1.6-1.6 2.5 2.5-1.6 1.6" />
    </Icon>
  ),
  clear: (
    <Icon>
      <path d="M6.4 12.6H14M2.2 9.6l4.6 3 5-6.9-4.6-3z" />
      <path d="M4.6 6.1 9 9" />
    </Icon>
  ),
  undo: (
    <Icon>
      <path d="M3 7.5h6.5a3.5 3.5 0 0 1 0 7H6M3 7.5l3-3M3 7.5l3 3" />
    </Icon>
  ),
  redo: (
    <Icon>
      <path d="M13 7.5H6.5a3.5 3.5 0 0 0 0 7H10M13 7.5l-3-3M13 7.5l-3 3" />
    </Icon>
  ),
  chevron: (
    <Icon>
      <path d="M4 6.5 8 10.5l4-4" />
    </Icon>
  ),
  more: (
    <Icon>
      <circle cx="3.2" cy="8" r="1.15" fill="currentColor" stroke="none" />
      <circle cx="8" cy="8" r="1.15" fill="currentColor" stroke="none" />
      <circle cx="12.8" cy="8" r="1.15" fill="currentColor" stroke="none" />
    </Icon>
  ),
} as const;

export type IconName = keyof typeof icons;
