import { useState } from "react";

interface TooltipProps {
  content: string;
  side?: "top" | "right" | "bottom" | "left";
  children: React.ReactNode;
}

export function Tooltip({ content, side = "top", children }: TooltipProps) {
  const [visible, setVisible] = useState(false);

  return (
    <span
      className="tooltip-anchor"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span className={`tooltip tooltip-${side}`} role="tooltip">
          {content}
        </span>
      )}
    </span>
  );
}

/** Small question-mark icon that shows a tooltip on hover. */
export function HelpIcon({
  content,
  side = "right",
}: {
  content: string;
  side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <Tooltip content={content} side={side}>
      <span className="help-icon" tabIndex={0} aria-label={content}>
        ?
      </span>
    </Tooltip>
  );
}
