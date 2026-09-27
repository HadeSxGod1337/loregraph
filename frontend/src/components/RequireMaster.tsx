import { useEffect, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { getAccessToken } from "../lib/authStorage";

/** True when the SPA is reached on the machine where the backend runs.
 * The backend trusts loopback unconditionally (see loregraph.api.security),
 * so no token is needed and requiring one would force a pointless login
 * every time the DM sits down at their own desk. */
function isLoopback(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  return host === "localhost" || host === "127.0.0.1" || host === "::1";
}

/** Guard for the DM-facing layout. On a non-loopback origin it redirects
 * to /login?from=<current> when no access token is present. The "from"
 * parameter is what LoginPage reads to send the DM back where they were
 * headed. On loopback it is a no-op: the backend already trusts the caller,
 * and a fresh browser profile would otherwise be stuck on the login form
 * for no reason.
 *
 * The check is synchronous (just a localStorage read), so there is no
 * loading flash: either the children render or the redirect is issued in
 * the same tick. */
export function RequireMaster({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();

  const needsToken = !isLoopback();
  const hasToken = getAccessToken() !== null;
  const blocked = needsToken && !hasToken;

  useEffect(() => {
    if (blocked) {
      const from = encodeURIComponent(location.pathname + location.search);
      navigate(`/login?from=${from}`, { replace: true });
    }
  }, [blocked, navigate, location.pathname, location.search]);

  // While the redirect is in flight, render nothing rather than a broken
  // page that would immediately fire a batch of 401s.
  if (blocked) return null;

  return <>{children}</>;
}