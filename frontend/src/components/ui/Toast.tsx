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

interface ToastItem {
  id: number;
  text: string;
  kind: ToastKind;
}

type PushToast = (text: string, kind?: ToastKind) => void;

const ToastContext = createContext<PushToast>(() => {});

const TOAST_LIFETIME_MS = 3500;

/** App-wide feedback channel: one small stack in the corner, auto-dismissed.
 * Every mutation that used to finish silently reports here instead. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const push = useCallback<PushToast>((text, kind = "success") => {
    const id = nextId.current++;
    setToasts((prev) => [...prev, { id, text, kind }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, TOAST_LIFETIME_MS);
  }, []);

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
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): PushToast {
  return useContext(ToastContext);
}
