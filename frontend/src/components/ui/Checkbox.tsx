import type { InputHTMLAttributes } from "react";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
}

/** Styled checkbox that works inside any parent layout (settings-page
 * column-direction labels, dialog full-width inputs, etc.) by hiding
 * the native input and rendering a custom box via CSS. */
export function Checkbox({ label, className, ...rest }: CheckboxProps) {
  return (
    <label className={`checkbox-wrapper${className ? ` ${className}` : ""}`}>
      <input type="checkbox" {...rest} />
      <span className="checkbox-box" aria-hidden="true" />
      <span className="checkbox-label">{label}</span>
    </label>
  );
}
