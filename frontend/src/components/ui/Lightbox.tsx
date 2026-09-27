import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { Icon } from "./Icon";

interface LightboxState {
  src: string;
  alt: string;
}

interface LightboxContextValue {
  open: (src: string, alt?: string) => void;
}

const LightboxContext = createContext<LightboxContextValue | null>(null);

const MIN_USER_SCALE = 0.25;
const MAX_USER_SCALE = 16;
const ZOOM_STEP = 1.2;

/** Full-screen image viewer with map-style zoom and pan.
 *
 * The <img> is laid out at its natural pixel size, NOT fitted with
 * max-width/height — fitting that way makes the browser rasterise a
 * container-sized copy, and `transform: scale(3)` then magnifies that
 * small raster (blurry). At natural size the full-resolution pixels stay
 * available, and the fit-to-screen baseline is a `fitScale` we compute on
 * load and fold into the same transform as the user's zoom. Zooming is
 * therefore always scaling the source, never a preview of it. */
export function LightboxProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LightboxState | null>(null);

  useEffect(() => {
    if (!state) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setState(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [state]);

  return (
    <LightboxContext.Provider
      value={{ open: (src, alt = "") => setState({ src, alt }) }}
    >
      {children}
      {state && <LightboxViewer state={state} onClose={() => setState(null)} />}
    </LightboxContext.Provider>
  );
}

function LightboxViewer({
  state,
  onClose,
}: {
  state: LightboxState;
  onClose: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  // fitScale: multiplies to make natural size fit the viewport on load.
  // userScale: the user's own zoom on top of that (1.0 = "fits, as opened").
  const [fitScale, setFitScale] = useState(1);
  const [userScale, setUserScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const [isPanning, setIsPanning] = useState(false);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(
    null,
  );

  const panStart = useRef<{ x: number; y: number; tx: number; ty: number } | null>(
    null,
  );
  const movedRef = useRef(false);
  const startedOnImage = useRef(false);

  useEffect(() => {
    setFitScale(1);
    setUserScale(1);
    setTx(0);
    setTy(0);
    setNaturalSize(null);
  }, [state.src]);

  function effectiveScale(): number {
    return fitScale * userScale;
  }

  function clamp(txVal: number, tyVal: number, user: number): [number, number] {
    const cont = containerRef.current;
    if (!cont || !naturalSize) return [txVal, tyVal];
    const eff = fitScale * user;
    const scaledW = naturalSize.w * eff;
    const scaledH = naturalSize.h * eff;
    const cw = cont.clientWidth;
    const ch = cont.clientHeight;
    if (scaledW <= cw && scaledH <= ch) return [0, 0];
    const maxX = Math.max(0, (scaledW - cw) / 2);
    const maxY = Math.max(0, (scaledH - ch) / 2);
    return [
      Math.max(-maxX, Math.min(maxX, txVal)),
      Math.max(-maxY, Math.min(maxY, tyVal)),
    ];
  }

  function zoomAt(clientX: number, clientY: number, factor: number) {
    const cont = containerRef.current;
    if (!cont) return;
    const rect = cont.getBoundingClientRect();
    const cx = clientX - rect.left - rect.width / 2;
    const cy = clientY - rect.top - rect.height / 2;

    const eff = effectiveScale();
    const worldX = (cx - tx) / eff;
    const worldY = (cy - ty) / eff;

    const next = Math.max(
      MIN_USER_SCALE,
      Math.min(MAX_USER_SCALE, userScale * factor),
    );
    if (next === userScale) return;

    const eff2 = fitScale * next;
    const ntx = cx - worldX * eff2;
    const nty = cy - worldY * eff2;
    const [ftx, fty] = clamp(ntx, nty, next);
    setUserScale(next);
    setTx(ftx);
    setTy(fty);
  }

  function zoomCenter(factor: number) {
    const cont = containerRef.current;
    if (!cont) return;
    const rect = cont.getBoundingClientRect();
    zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor);
  }

  function reset() {
    setUserScale(1);
    setTx(0);
    setTy(0);
  }

  function handleLoad(e: React.SyntheticEvent<HTMLImageElement>) {
    const img = e.currentTarget;
    const cont = containerRef.current;
    if (!cont) return;
    const fit = Math.min(
      cont.clientWidth / img.naturalWidth,
      cont.clientHeight / img.naturalHeight,
      1,
    );
    setFitScale(fit);
    setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
  }

  function onWheel(e: React.WheelEvent<HTMLDivElement>) {
    e.preventDefault();
    const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
    zoomAt(e.clientX, e.clientY, factor);
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    const cont = containerRef.current;
    if (!cont) return;
    cont.setPointerCapture(e.pointerId);
    panStart.current = { x: e.clientX, y: e.clientY, tx, ty };
    movedRef.current = false;
    startedOnImage.current = e.target === imgRef.current;
    setIsPanning(true);
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!panStart.current) return;
    const dx = e.clientX - panStart.current.x;
    const dy = e.clientY - panStart.current.y;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) movedRef.current = true;
    const [ctx, cty] = clamp(
      panStart.current.tx + dx,
      panStart.current.ty + dy,
      userScale,
    );
    setTx(ctx);
    setTy(cty);
  }

  function onPointerUp() {
    if (!panStart.current) return;
    const wasMoved = movedRef.current;
    const wasImage = startedOnImage.current;
    panStart.current = null;
    startedOnImage.current = false;
    setIsPanning(false);
    if (!wasMoved && !wasImage) onClose();
  }

  const cursor = isPanning ? "grabbing" : userScale > 1 ? "grab" : "zoom-out";
  const eff = effectiveScale();

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-modal="true"
      onWheel={onWheel}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.9)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 2000,
        overflow: "hidden",
        cursor,
        touchAction: "none",
        userSelect: "none",
      }}
    >
      <img
        ref={imgRef}
        src={state.src}
        alt={state.alt}
        draggable={false}
        onLoad={handleLoad}
        onDoubleClick={(e) => {
          e.stopPropagation();
          if (userScale > 1) reset();
          else zoomAt(e.clientX, e.clientY, 2);
        }}
        style={{
          maxWidth: "none",
          maxHeight: "none",
          transform: `translate(${tx}px, ${ty}px) scale(${eff})`,
          transformOrigin: "center center",
          pointerEvents: "auto",
          willChange: "transform",
          imageRendering: "auto",
        }}
      />

      <div
        onPointerDown={(e) => e.stopPropagation()}
        style={{
          position: "absolute",
          top: 16,
          right: 16,
          display: "flex",
          gap: 6,
          alignItems: "center",
          background: "rgba(0, 0, 0, 0.5)",
          borderRadius: 10,
          padding: 6,
        }}
      >
        <ControlButton
          label="−"
          title="Zoom out"
          onClick={() => zoomCenter(1 / ZOOM_STEP)}
        />
        <span
          style={{
            color: "#fff",
            fontVariantNumeric: "tabular-nums",
            fontSize: 12,
            minWidth: 44,
            textAlign: "center",
            opacity: 0.8,
          }}
        >
          {Math.round(userScale * 100)}%
        </span>
        <ControlButton
          label="+"
          title="Zoom in"
          onClick={() => zoomCenter(ZOOM_STEP)}
        />
        <ControlButton label="1:1" title="Fit to screen" onClick={reset} />
        <ControlButton
          label=""
          title="Close"
          icon={<Icon name="x" size={18} />}
          onClick={onClose}
        />
      </div>
    </div>
  );
}

function ControlButton({
  label,
  title,
  icon,
  onClick,
}: {
  label: string;
  title: string;
  icon?: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      style={{
        background: "transparent",
        border: "1px solid rgba(255,255,255,0.25)",
        color: "#fff",
        borderRadius: 6,
        padding: "4px 10px",
        fontSize: 13,
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: 32,
        minHeight: 28,
      }}
    >
      {icon ?? label}
    </button>
  );
}

export function useLightbox(): LightboxContextValue {
  const ctx = useContext(LightboxContext);
  if (!ctx) throw new Error("useLightbox must be used within a LightboxProvider");
  return ctx;
}