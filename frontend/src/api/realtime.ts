import { API_URL } from "./client";

export interface ProjectEvent<TPayload = Record<string, unknown>> {
  seq: number;
  type: string;
  project_id: string;
  payload: TPayload;
  ts: number;
}

/** http(s):// -> ws(s):// against the same API host, so dev/prod both work
 * without a separate WS env var. */
export function wsUrl(projectId: string, catchUpFrom?: number): string {
  const base = API_URL.replace(/^http/, "ws");
  const url = new URL(`${base}/api/ws/projects/${projectId}`);
  if (catchUpFrom !== undefined) {
    url.searchParams.set("catch_up_from", String(catchUpFrom));
  }
  return url.toString();
}
