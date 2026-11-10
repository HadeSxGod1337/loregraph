import { useEffect, useState } from "react";

export type EmbedStatus = "loading" | "embedded" | "blocked";

/** `loaded` is trusted the moment it fires — the caller is expected to pass
 * a URL actually meant for third-party embedding (Notion's `/ebd/` route,
 * not its canonical page URL, which refuses outside frames entirely and
 * would never fire `load` with real content). maxWaitMs is purely a safety
 * net for the embed never starting at all — a network hiccup, an
 * ad-blocker rule on the provider's domain, or the provider changing its
 * embed policy later — not a signal used to second-guess a `load` that did
 * fire. */
export function deriveEmbedStatus(loaded: boolean, timedOut: boolean): EmbedStatus {
  if (loaded) return "embedded";
  return timedOut ? "blocked" : "loading";
}

export interface UseEmbedLoadStatusOptions {
  maxWaitMs?: number;
}

export function useEmbedLoadStatus(
  url: string,
  { maxWaitMs = 8000 }: UseEmbedLoadStatusOptions = {},
) {
  const [loaded, setLoaded] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    setLoaded(false);
    setTimedOut(false);
    const timer = window.setTimeout(() => setTimedOut(true), maxWaitMs);
    return () => window.clearTimeout(timer);
  }, [url, maxWaitMs]);

  return {
    status: deriveEmbedStatus(loaded, timedOut),
    onIframeLoad: () => setLoaded(true),
  };
}
