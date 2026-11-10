// Where the DM's access and refresh tokens live between page loads.
//
// Chosen over cookies because the two backends (this SPA, Loregraph, and the
// Go auth service) run on different ports in dev, and cross-origin cookies
// need SameSite=None + HTTPS + a shared domain to work — too much ceremony
// for a single-user DM tool. The refresh token sitting in localStorage is a
// real trade-off (XSS could steal it), accepted here because the threat model
// is "one DM on their own machine", not "multi-tenant SaaS".
//
// Every reader tolerates localStorage being unavailable: Safari private mode
// throws on write, and a corrupted value should log the user out rather than
// crash the whole SPA.

const ACCESS_KEY = "lg_auth_access";
const REFRESH_KEY = "lg_auth_refresh";

export interface StoredTokens {
  accessToken: string;
  refreshToken: string;
}

function readKey(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeKey(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // ignore: storage might be full, disabled, or in private mode
  }
}

function removeKey(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export function getAccessToken(): string | null {
  return readKey(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return readKey(REFRESH_KEY);
}

export function setTokens(tokens: StoredTokens): void {
  writeKey(ACCESS_KEY, tokens.accessToken);
  writeKey(REFRESH_KEY, tokens.refreshToken);
}

export function clearTokens(): void {
  removeKey(ACCESS_KEY);
  removeKey(REFRESH_KEY);
}