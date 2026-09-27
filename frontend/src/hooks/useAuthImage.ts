import { useEffect, useState } from "react";

import { API_URL } from "../api/client";
import { getAccessToken } from "../lib/authStorage";

/** Cache of blob URLs by relative path.
 *
 * A plain <img src> can't carry an Authorization header, so any image behind
 * the master guard fails on a non-loopback origin (the browser sends no token
 * and the backend answers 401). This hook fetches the file through the same
 * auth path as the rest of the API, wraps the response in an object URL, and
 * hands that to <img>. The cache means the same picture shown in the list,
 * the graph and the entity page is fetched once, not three times.
 *
 * Object URLs are never revoked: they live for the page session, sized for
 * the number of distinct attachments a campaign holds, and revoking them
 * would break every other mounted <img> still pointing at the same URL. */
const cache = new Map<string, Promise<string>>();

function loadBlobUrl(path: string): Promise<string> {
  let pending = cache.get(path);
  if (!pending) {
    const token = getAccessToken();
    const headers: Record<string, string> = token
      ? { Authorization: `Bearer ${token}` }
      : {};
    // credentials: "include" so the player cookie (lg_play) travels along —
    // on the /play/ pages there is no Bearer token at all, only that cookie,
    // and a cookie-less fetch would answer 401 to every icon.
    pending = fetch(API_URL + path, { headers, credentials: "include" })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.blob();
      })
      .then((blob) => URL.createObjectURL(blob))
      .catch((error) => {
        // Drop the failed promise so a later remount can retry — the failure
        // may be transient (server restarted, token refreshed).
        cache.delete(path);
        throw error;
      });
    cache.set(path, pending);
  }
  return pending;
}

/** Resolve a relative attachment path (e.g. "/files/<entity>/<file>.jpg")
 * to a blob URL usable as an <img> src. Returns null until the fetch
 * settles, and stays null for a null/undefined path or a fetch failure —
 * callers fall back to their placeholder in that case. */
export function useAuthImage(path: string | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!path) {
      setUrl(null);
      return;
    }
    let cancelled = false;
    loadBlobUrl(path)
      .then((result) => {
        if (!cancelled) setUrl(result);
      })
      .catch(() => {
        // A missing or forbidden file: leave url null and let the caller
        // render its fallback (initial letter, generic icon, ...).
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  return url;
}