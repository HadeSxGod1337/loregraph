import type { ReactNode } from "react";

/** "top-start" hangs the bubble from the anchor's left edge rather than
 * centring it — what a left-aligned toolbar needs, since a centred label is
 * wider than an icon button and would overhang the container. */
type Placement = "top" | "top-start" | "bottom" | "left" | "right";

/** Hover/focus label for a control that shows only an icon.
 *
 * The bubble is decoration: the control itself must still carry an
 * `aria-label` with the same text, or the button has no accessible name.
 * That's why this one is `aria-hidden` — otherwise assistive tech reads the
 * label twice. Prefer this over the native `title` attribute, which appears
 * after a browser-chosen delay and can't be styled.
 *
 * Placement is not collision-aware. `.panel-head` clips its children, so
 * inside it only "top" stays visible.
 */
export function Tooltip({
  label,
  placement = "top",
  children,
}: {
  label: string;
  placement?: Placement;
  children: ReactNode;
}) {
  return (
    <span className="tooltip-anchor">
      {children}
      <span className={"tooltip tooltip-" + placement} aria-hidden="true">
        {label}
      </span>
    </span>
  );
}
