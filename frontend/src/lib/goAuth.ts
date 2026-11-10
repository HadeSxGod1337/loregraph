// Thin client for the Go auth service. Lives next to authStorage rather than
// under api/ because it talks to a different backend: the DM authenticates
// against the Go service, everything else (Loregraph's own endpoints) goes
// through api/client.ts. Keeping the two apart makes it obvious at a glance
// which calls carry a Bearer token that Loregraph will verify locally.
//
// Endpoint shapes come from the Go service's HandleLogin/HandleRefresh/
// HandleLogout (see its internal/transport/rest package).

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "./authStorage";

// In dev, .env.development points this at http://localhost:8080 — the Go
// service runs as its own process and its CORS middleware covers the
// two-origin case. In a packaged install VITE_GO_AUTH_URL is unset, so the
// value becomes /api/go-auth: a relative URL, same origin as the SPA,
// forwarded by the backend proxy to the loopback-only Go service (see
// backend loregraph/api/go_auth_proxy.py).
const GO_AUTH_URL =
  import.meta.env.VITE_GO_AUTH_URL || "/api/go-auth";

interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  user: { email: string; userId: string };
}

interface RefreshResponse {
  accessToken: string;
  refreshToken: string;
}

export class GoAuthError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "GoAuthError";
    this.status = status;
  }
}

async function parseError(response: Response): Promise<string> {
  // The Go service writes errors with http.Error, so the body is plain text,
  // not JSON. Fall back to statusText when the body is empty.
  try {
    const text = await response.text();
    return text.trim() || response.statusText;
  } catch {
    return response.statusText;
  }
}

/** Exchange email + password for a token pair. On success the pair is stored
 * in localStorage; the caller usually only needs to navigate somewhere. */
export async function loginGo(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const response = await fetch(`${GO_AUTH_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new GoAuthError(response.status, await parseError(response));
  }
  const data = (await response.json()) as LoginResponse;
  setTokens({
    accessToken: data.accessToken,
    refreshToken: data.refreshToken,
  });
  return data;
}

/** Create a new account on the Go auth service.
 *
 * Unlike loginGo, tokens returned by /register are deliberately *not*
 * stored: the Go service creates every account with role "user", and the
 * backend rejects any non-master role, so holding the token would land the
 * caller on "/" only to receive a batch of 401s. The registration flow
 * tells the user instead that an administrator has to promote the account
 * (edit users.json, flip "role" to "master"), and to come back to /login
 * afterwards.
 *
 * Throws GoAuthError on any non-2xx response so the page can distinguish
 * "email taken" (409) from "registration closed" (403) from a network
 * failure. */
export async function registerGo(
  email: string,
  password: string,
): Promise<void> {
  const response = await fetch(`${GO_AUTH_URL}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new GoAuthError(response.status, await parseError(response));
  }
  // Body contains accessToken/refreshToken/user, but see the doc comment
  // above: we intentionally drop them.
}

/** Ask the Go service for a new access token using the stored refresh token.
 * On success the old pair is replaced. Returns the new access token so the
 * caller (the 401 interceptor in client.ts) can retry the failed request. */
export async function refreshGo(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  const response = await fetch(`${GO_AUTH_URL}/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken }),
  });
  if (!response.ok) {
    // Refresh token rejected (expired, revoked, used). Wipe both tokens so
    // the app doesn't keep retrying with a dead refresh, and let the caller
    // redirect to /login.
    clearTokens();
    return null;
  }
  const data = (await response.json()) as RefreshResponse;
  setTokens({
    accessToken: data.accessToken,
    refreshToken: data.refreshToken,
  });
  return data.accessToken;
}

/** Best-effort server-side logout: revoke the refresh token, then clear
 * local state unconditionally. A network error here shouldn't trap the user
 * in a logged-in shell — losing the local tokens is enough. */
export async function logoutGo(): Promise<void> {
  const refreshToken = getRefreshToken();
  if (refreshToken) {
    try {
      await fetch(`${GO_AUTH_URL}/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken }),
      });
    } catch {
      // ignore: clearing local tokens is what actually logs the user out
    }
  }
  clearTokens();
}

export interface UserSummary {
  id: string;
  email: string;
  role: "user" | "master" | "owner";
  createdAt: string;
}

/** List all accounts. Owner-only: a master gets 403 back and the caller
 * turns that into "you can't see this", not an error toast. */
export async function listUsers(): Promise<UserSummary[]> {
  const token = getAccessToken();
  if (!token) throw new GoAuthError(401, "Not signed in");

  const response = await fetch(`${GO_AUTH_URL}/users`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new GoAuthError(response.status, await parseError(response));
  }
  const body = (await response.json()) as { users: UserSummary[] };
  return body.users;
}

/** Change someone's role. The Go service refuses when the caller is not an
 * owner and when the target is the caller's own account; both surface as
 * GoAuthError with a 403, and the dialog renders the server's message. */
export async function changeUserRole(
  userId: string,
  role: UserSummary["role"],
): Promise<void> {
  const token = getAccessToken();
  if (!token) throw new GoAuthError(401, "Not signed in");

  const response = await fetch(`${GO_AUTH_URL}/users/${userId}/role`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ role }),
  });
  if (!response.ok) {
    throw new GoAuthError(response.status, await parseError(response));
  }
}

/** Decode the JWT payload to find the current user's own id. Used to
 * disable the role selector on your own row — the server refuses self-
 * changes anyway, but a disabled control reads better than a 403 after a
 * click. Returns null on any parse failure; the caller then leaves every
 * row enabled and lets the server do the enforcing. */
export function getOwnUserId(): string | null {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    // JWT uses base64url, atob wants base64 — pad and swap as needed.
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const decoded = JSON.parse(atob(padded)) as { sub?: string };
    return decoded.sub ?? null;
  } catch {
    return null;
  }
}

/** Remove an account. Owner-only; the server refuses self-deletion. */
export async function deleteUser(userId: string): Promise<void> {
  const token = getAccessToken();
  if (!token) throw new GoAuthError(401, "Not signed in");

  const response = await fetch(`${GO_AUTH_URL}/users/${userId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new GoAuthError(response.status, await parseError(response));
  }
}