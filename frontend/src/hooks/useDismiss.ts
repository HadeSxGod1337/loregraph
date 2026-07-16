import { useEffect, type RefObject } from "react";

/** Closes an open popover/menu on outside click or Escape. */
export function useDismiss(
  open: boolean,
  ref: RefObject<HTMLElement | null>,
  onDismiss: () => void,
): void {
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onDismiss();
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onDismiss();
    }
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, ref, onDismiss]);
}
