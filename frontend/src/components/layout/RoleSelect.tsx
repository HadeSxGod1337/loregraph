import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Icon } from "../ui/Icon";

export type Role = "user" | "master" | "owner";

const ROLES: Role[] = ["user", "master", "owner"];

interface RoleSelectProps {
  value: Role;
  disabled?: boolean;
  onChange: (role: Role) => void;
}

/** Small controlled dropdown for the three roles. Not a native <select>:
 * the browser paints that list itself and ignores styling, so it stood out
 * from every other control in the app. Not a datalist either: that only
 * suggests while typing, and a role is a pick-from-list value, not free
 * text.
 *
 * Deliberately local to the admin dialog — generalising it into a shared
 * component would earn its keep the moment a second caller appears, and
 * there isn't one yet. */
export function RoleSelect({ value, disabled, onChange }: RoleSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on outside click. Capture-phase listener so a click on any other
  // interactive control still reaches it first — the dropdown only reacts
  // to clicks that are not inside itself.
  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function pick(role: Role) {
    setOpen(false);
    if (role !== value) onChange(role);
  }

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 10px",
          fontSize: 13,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-control)",
          cursor: disabled ? "default" : "pointer",
          color: "inherit",
        }}
      >
        <span>{t(`users.role.${value}`)}</span>
        <Icon name="chevron-down" size={14} />
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            right: 0,
            minWidth: "100%",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-control)",
            boxShadow: "var(--shadow)",
            zIndex: 1100,
            overflow: "hidden",
          }}
        >
          {ROLES.map((role) => (
            <button
              key={role}
              type="button"
              onClick={() => pick(role)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "6px 10px",
                fontSize: 13,
                background: role === value ? "var(--accent-soft)" : "transparent",
                color: "inherit",
                border: "none",
                cursor: "pointer",
              }}
              onMouseEnter={(e) => {
                if (role !== value) {
                  e.currentTarget.style.background = "var(--bg-subtle)";
                }
              }}
              onMouseLeave={(e) => {
                if (role !== value) {
                  e.currentTarget.style.background = "transparent";
                }
              }}
            >
              {t(`users.role.${role}`)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}