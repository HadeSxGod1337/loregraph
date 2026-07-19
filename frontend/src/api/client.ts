export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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

  const init: RequestInit = { method };
  if (json !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(json);
  } else if (body !== undefined) {
    init.body = body;
  }

  const response = await fetch(buildUrl(path, params), init);

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
  const response = await fetch(API_URL + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
