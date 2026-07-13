import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

interface ConfirmDialogProps {
  title: string;
  body: string;
  confirmLabel: string;
  /** When set, the confirm button stays disabled until the user types this
   * exact string — the "type the name to delete" pattern. */
  requireText?: string;
  requirePlaceholder?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Modal confirmation for destructive actions. The filled-red confirm button
 * is allowed here and only here (see the button system in index.css). */
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  requireText,
  requirePlaceholder,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState("");
  const confirmBlocked = busy || (requireText !== undefined && typed !== requireText);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onCancel]);

  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div
        className="dialog"
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{title}</h2>
        <p>{body}</p>
        {requireText !== undefined && (
          <input
            autoFocus
            placeholder={requirePlaceholder}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !confirmBlocked) onConfirm();
            }}
          />
        )}
        <div className="dialog-actions">
          <button type="button" className="button-ghost" onClick={onCancel}>
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className="button-danger-solid"
            autoFocus={requireText === undefined}
            disabled={confirmBlocked}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
