import { useEffect, useState } from "react";

export type EmbedStatus = "loading" | "embedded" | "blocked";

/** A frame that fires `load` before minEmbedMs has passed is almost never
 * real content — third-party providers that refuse framing (a
 * frame-ancestors CSP or X-Frame-Options) still resolve the frame
 * navigation immediately, just onto an empty/error document. A frame that
 * never fires `load` at all before maxWaitMs is treated the same way. Both
 * fall back to "open in a new tab" instead of leaving a blank frame on
 * screen. A real page — Notion's public pages included — pulls down enough
 * script to take noticeably longer than that. */
export function deriveEmbedStatus(
  loaded: boolean,
  pastMinWindow: boolean,
  timedOut: boolean,
): EmbedStatus {
  if (loaded) return pastMinWindow ? "embedded" : "blocked";
  return timedOut ? "blocked" : "loading";
}

export interface UseEmbedLoadStatusOptions {
  minEmbedMs?: number;
  maxWaitMs?: number;
}

export function useEmbedLoadStatus(
  url: string,
  { minEmbedMs = 900, maxWaitMs = 8000 }: UseEmbedLoadStatusOptions = {},
) {
  const [loaded, setLoaded] = useState(false);
  const [pastMinWindow, setPastMinWindow] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    setLoaded(false);
    setPastMinWindow(false);
    setTimedOut(false);
    const minTimer = window.setTimeout(() => setPastMinWindow(true), minEmbedMs);
    const maxTimer = window.setTimeout(() => setTimedOut(true), maxWaitMs);
    return () => {
      window.clearTimeout(minTimer);
      window.clearTimeout(maxTimer);
    };
  }, [url, minEmbedMs, maxWaitMs]);

  return {
    status: deriveEmbedStatus(loaded, pastMinWindow, timedOut),
    onIframeLoad: () => setLoaded(true),
  };
}
