import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { Icon } from "./Icon";

type ToastKind = "success" | "error";

/** One button on the toast, for a change worth taking back — an undo the DM
 * can reach without hunting for what the app just wrote. */
export interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastItem {
  id: number;
  text: string;
  kind: ToastKind;
  action?: ToastAction;
}

type PushToast = (text: string, kind?: ToastKind, action?: ToastAction) => void;

const ToastContext = createContext<PushToast>(() => {});

const TOAST_LIFETIME_MS = 3500;
/** An undo has to outlive the glance that notices it. */
const TOAST_WITH_ACTION_LIFETIME_MS = 8000;

/** App-wide feedback channel: one small stack in the corner, auto-dismissed.
 * Every mutation that used to finish silently reports here instead. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback<PushToast>(
    (text, kind = "success", action) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev, { id, text, kind, action }]);
      setTimeout(
        () => dismiss(id),
        action ? TOAST_WITH_ACTION_LIFETIME_MS : TOAST_LIFETIME_MS,
      );
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={toast.kind === "error" ? "toast toast-error" : "toast"}
          >
            <span className="toast-mark">
              <Icon name={toast.kind === "error" ? "alert" : "check"} size={11} />
            </span>
            {toast.text}
            {toast.action && (
              <button
                type="button"
                className="toast-action"
                onClick={() => {
                  toast.action?.onClick();
                  dismiss(toast.id);
                }}
              >
                {toast.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): PushToast {
  return useContext(ToastContext);
}
