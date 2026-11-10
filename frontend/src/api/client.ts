import { getAccessToken } from "../lib/authStorage";
import { refreshGo } from "../lib/goAuth";

// Same origin as the page: in the packaged setup the backend serves this
// bundle itself, so the API is wherever the page came from — localhost for the
// DM, the LAN or public address for a player, http or https, whatever port.
// Hardcoding a host here is what sent every player's browser to its own
// machine. VITE_API_URL overrides it for a dev run where Vite (5173) and the
// backend (8000) are separate processes — see frontend/.env.development.
export const API_URL =
  import.meta.env.VITE_API_URL ??
  (typeof window !== "undefined" ? window.location.origin : "");

/** Authorization header for Loregraph endpoints, when a DM token is present.
 *
 * Absent on loopback, where the backend trusts the local machine and no
 * token is required — this is the "DM on their own desk" case. Present
 * everywhere else, so a DM reached over the LAN or from outside carries the
 * token the Go service issued at login (see lib/goAuth.ts).
 *
 * Not applied to player endpoints: those authenticate with a session cookie
 * the play-session exchange sets, and adding an unrelated Bearer token would
 * be noise at best.
 */
function authHeaders(): Record<string, string> {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Single-flight wrapper around refreshGo: N parallel 401s share one
 * refresh call instead of racing. The Go service's refresh tokens are
 * one-shot, so racing would invalidate all but one caller's token and
 * log the user out under load — exactly when the app looks busiest. */
let refreshInFlight: Promise<string | null> | null = null;

function refreshOnce(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = refreshGo().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** Player endpoints authenticate with a session cookie, not a DM token.
 * A 401 from those must not trigger a master-token refresh or a redirect
 * to /login — the player is on /play/:token and stays there. */
function isPlayerPath(path: string): boolean {
  return path.startsWith("/api/play/");
}

function redirectToLogin(): void {
  if (
    typeof window !== "undefined" &&
    !window.location.pathname.startsWith("/login")
  ) {
    window.location.assign("/login");
  }
}

export class ApiError extends Error {
  status: number;
  /** Machine-readable code from the backend's error body (see
   * loregraph.exceptions.error_code) — undefined for errors FastAPI itself
   * raises (e.g. request validation) before reaching our handlers. Use
   * translateApiError (src/i18n/eventText.ts) to render this for a user. */
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  json?: unknown;
  body?: FormData;
  params?: Record<string, string | number | string[] | undefined>;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = new URL(API_URL + path);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined) continue;
      if (Array.isArray(value)) {
        for (const v of value) url.searchParams.append(key, v);
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", json, body, params } = options;

  // GitHub Pages demo: no server exists, so every call is answered by the
  // in-memory fake backend instead. The dynamic import keeps demo code out of
  // the real bundle (import.meta.env.VITE_DEMO folds to false there).
  if (import.meta.env.VITE_DEMO) {
    const { demoRequest } = await import("./demo/backend");
    return demoRequest(method, path, params, json ?? body) as Promise<T>;
  }

  // credentials: player sessions authenticate with a cookie the play-session
  // endpoint sets; including it is harmless for the loopback DM requests.
  const init: RequestInit = { method, credentials: "include" };
  if (json !== undefined) {
    init.headers = { "Content-Type": "application/json", ...authHeaders() };
    init.body = JSON.stringify(json);
  } else if (body !== undefined) {
    init.headers = authHeaders();
    init.body = body;
  } else {
    init.headers = authHeaders();
  }

  let response = await fetch(buildUrl(path, params), init);

  // Access token expired (or absent on a non-loopback origin): try one
  // refresh, then retry the original request once with the new token.
  // Not applied to player endpoints — their 401 means "session expired",
  // not "refresh the DM".
  if (response.status === 401 && !isPlayerPath(path)) {
    const newToken = await refreshOnce();
    if (newToken === null) {
      redirectToLogin();
      throw new ApiError(
        401,
        `Session expired (${method} ${path})`,
      );
    }
    init.headers = {
      ...(init.headers as Record<string, string> | undefined),
      Authorization: `Bearer ${newToken}`,
    };
    response = await fetch(buildUrl(path, params), init);
  }

  if (!response.ok) {
    let detail = response.statusText;
    let code: string | undefined;
    try {
      const errorBody = (await response.json()) as { detail?: string; code?: string };
      detail = errorBody.detail ?? detail;
      code = errorBody.code;
    } catch {
      // response had no JSON body; fall back to statusText
    }
    // A bare "Not Found" is useless in the UI — always say what was called.
    throw new ApiError(
      response.status,
      `${detail} (${method} ${path} → HTTP ${response.status})`,
      code,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** POST an SSE endpoint and feed parsed events to the callback. EventSource
 * can't POST, so this reads the fetch body stream directly. Shared by the
 * agent chat endpoints and the bulk-import job endpoints — both stream the
 * same `data: {...}\n\n` framing, just with different event payload shapes. */
export async function streamSse<TEvent>(
  path: string,
  body: unknown,
  onEvent: (event: TEvent) => void,
): Promise<void> {
  if (import.meta.env.VITE_DEMO) {
    const { demoStream } = await import("./demo/backend");
    return demoStream<TEvent>(path, body, onEvent);
  }

  let response = await fetch(API_URL + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });

  if (response.status === 401 && !isPlayerPath(path)) {
    const newToken = await refreshOnce();
    if (newToken === null) {
      redirectToLogin();
      throw new ApiError(401, `Session expired (POST ${path})`);
    }
    response = await fetch(API_URL + path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${newToken}`,
      },
      body: JSON.stringify(body),
    });
  }

  if (!response.ok || !response.body) {
    let detail = response.statusText;
    let code: string | undefined;
    try {
      const errorBody = (await response.json()) as { detail?: string; code?: string };
      detail = errorBody.detail ?? detail;
      code = errorBody.code;
    } catch {
      // no JSON body
    }
    throw new ApiError(
      response.status,
      `${detail} (POST ${path} → HTTP ${response.status})`,
      code,
    );
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (raw.startsWith("data: ")) {
        onEvent(JSON.parse(raw.slice(6)) as TEvent);
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export const apiClient = {
  get: <T>(path: string, params?: RequestOptions["params"]) =>
    request<T>(path, { method: "GET", params }),
  post: <T>(path: string, json?: unknown) => request<T>(path, { method: "POST", json }),
  postForm: <T>(path: string, body: FormData) =>
    request<T>(path, { method: "POST", body }),
  put: <T>(path: string, json?: unknown) => request<T>(path, { method: "PUT", json }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
