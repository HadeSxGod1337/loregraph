import type { InputHTMLAttributes } from "react";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
}

/** Styled checkbox that works inside any parent layout (settings-page
 * column-direction labels, dialog full-width inputs, etc.): the native
 * input stays in the DOM for accessibility (focus, keyboard, screen
 * readers) but is visually hidden, and the box next to it is drawn by the
 * .checkbox-* rules in App.css — the base styles live at the END of the
 * file so they win specificity ties against page-level `... label` rules. */
export function Checkbox({ label, className, title, disabled, ...rest }: CheckboxProps) {
  const classes = ["checkbox-wrapper"];
  if (disabled) classes.push("checkbox-disabled");
  if (className) classes.push(className);
  return (
    <label className={classes.join(" ")} title={title}>
      <input type="checkbox" disabled={disabled} {...rest} />
      <span className="checkbox-box" aria-hidden="true" />
      <span className="checkbox-label">{label}</span>
    </label>
  );
}
