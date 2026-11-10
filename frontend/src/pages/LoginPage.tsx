import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { GoAuthError, loginGo } from "../lib/goAuth";
import { getAccessToken } from "../lib/authStorage";

/** DM sign-in. Rendered outside <Layout> — before login there is no project
 * to show a sidebar for, and the layout's chrome would just be dead weight
 * around a single form.
 *
 * On loopback the backend already trusts the machine, but this page is still
 * reachable directly: a DM may want their session to survive switching to a
 * LAN address or leaving the house, in which case they come here on purpose. */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Where to go after a successful login. The 401 interceptor in
  // api/client.ts calls window.location.assign("/login"), which reloads the
  // page — React state is gone by then, so the target has to travel in the
  // URL. Default to the app root when there is no hint.
  const next = new URLSearchParams(location.search).get("from") || "/";

  // Already signed in? Bounce immediately. Runs in an effect rather than
  // inline so we don't call navigate() during render, which React 18 warns
  // about and can drop in StrictMode.
  useEffect(() => {
    if (getAccessToken()) {
      navigate(next, { replace: true });
    }
  }, [navigate, next]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await loginGo(email, password);
      navigate(next, { replace: true });
    } catch (err) {
      if (err instanceof GoAuthError) {
        if (err.status === 401) {
          setError(t("auth.error.invalidCredentials"));
        } else if (err.status >= 500) {
          setError(t("auth.error.server"));
        } else {
          setError(t("auth.error.generic"));
        }
      } else {
        // Network failure (fetch rejected): DNS, CORS, service down.
        setError(t("auth.error.network"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <div style={{ width: "100%", maxWidth: 360 }}>
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-card)",
            padding: 24,
            boxShadow: "var(--shadow)",
          }}
        >
          <h1 style={{ marginBottom: 4 }}>{t("auth.login.title")}</h1>
          <p
            style={{
              marginTop: 0,
              marginBottom: 20,
              color: "var(--text-muted)",
              fontSize: 13,
            }}
          >
            {t("auth.login.subtitle")}
          </p>

          <form
            onSubmit={handleSubmit}
            style={{ display: "flex", flexDirection: "column", gap: 14 }}
          >
            <label
              style={{ display: "flex", flexDirection: "column", gap: 4 }}
            >
              <span style={{ fontSize: 13 }}>{t("auth.login.email")}</span>
              <input
                type="email"
                required
                autoComplete="username"
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>

            <label
              style={{ display: "flex", flexDirection: "column", gap: 4 }}
            >
              <span style={{ fontSize: 13 }}>{t("auth.login.password")}</span>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>

            {error && (
              <div
                role="alert"
                className="error-text"
                style={{
                  background: "var(--bg-subtle)",
                  border: "1px solid var(--danger)",
                  borderRadius: "var(--radius-control)",
                  padding: "8px 10px",
                  fontSize: 13,
                }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              className="button-primary"
              disabled={submitting}
              style={{ marginTop: 4 }}
            >
              {submitting ? t("auth.login.submitting") : t("auth.login.submit")}
            </button>
          </form>
          <div
            style={{
              marginTop: 16,
              fontSize: 13,
              textAlign: "center",
              color: "var(--text-muted)",
            }}
          >
              <Link to={`/register${location.search}`}>
                {t("auth.login.noAccount")}
              </Link>
          </div>
        </div>
      </div>
    </div>
  );
}