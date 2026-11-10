import { useEffect, useRef, useState } from "react";

import { Icon } from "./Icon";

export interface KebabMenuItem {
  label: string;
  onClick: () => void;
  danger?: boolean;
}

/** A visual divider between two groups of items — e.g. layout actions vs.
 * hierarchy actions in the graph dock's menu. Purely presentational, no
 * label or click handler of its own. */
export interface KebabMenuSeparator {
  separator: true;
}

export type KebabMenuEntry = KebabMenuItem | KebabMenuSeparator;

/** "⋯" menu for secondary row actions — keeps destructive operations out of
 * the always-visible surface of a card. `placement` defaults to opening
 * downward (the original, still-used-elsewhere behavior); pass "up" for
 * triggers that sit at the bottom of their container, like the graph dock,
 * where a downward menu would open off-screen. */
export function KebabMenu({
  label,
  items,
  placement = "down",
}: {
  label: string;
  items: KebabMenuEntry[];
  placement?: "down" | "up";
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className={placement === "up" ? "kebab-menu upward" : "kebab-menu"} ref={rootRef}>
      <button
        type="button"
        className="icon-button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="more" />
      </button>
      {open && (
        <div className="kebab-menu-list" role="menu">
          {items.map((item, index) =>
            "separator" in item ? (
              <div key={`separator-${index}`} className="kebab-menu-separator" role="separator" />
            ) : (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                className={item.danger ? "danger" : undefined}
                onClick={() => {
                  setOpen(false);
                  item.onClick();
                }}
              >
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}
