import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { GoAuthError, registerGo } from "../lib/goAuth";

/** Account creation for the DM. Sibling of LoginPage, styled the same way,
 * and reachable from it by a link at the bottom.
 *
 * Two deliberate differences from LoginPage:
 * - No auto-redirect after success. The Go service creates every account
 *   with role "user"; the backend rejects non-master roles, so sending the
 *   new user to "/" would land them on a page that 401s everything. The
 *   page tells them what to do instead.
 * - No token handling. registerGo drops the returned pair on purpose (see
 *   lib/goAuth.ts), so there is nothing to store here. */
export function RegisterPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState(false);

  // Preserve the ?from= the login flow may have set, so switching between
  // the two forms doesn't lose the page the DM was originally heading to.
  const search = location.search;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    // Client-side check only for the one thing the server can't: password
    // confirmation. Everything else (email shape, password strength) is the
    // server's call — see domain.IsValidEmail / IsValidPassword.
    if (password !== confirm) {
      setError(t("auth.error.passwordMismatch"));
      return;
    }

    setSubmitting(true);
    try {
      await registerGo(email, password);
      setCreated(true);
    } catch (err) {
      if (err instanceof GoAuthError) {
        if (err.status === 409) {
          setError(t("auth.error.emailTaken"));
        } else if (err.status === 403) {
          setError(t("auth.error.registrationClosed"));
        } else if (err.status >= 500) {
          setError(t("auth.error.server"));
        } else {
          setError(t("auth.error.generic"));
        }
      } else {
        setError(t("auth.error.network"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (created) {
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
            <h1 style={{ marginBottom: 4 }}>{t("auth.register.createdTitle")}</h1>
            <p
              style={{
                marginTop: 0,
                marginBottom: 20,
                color: "var(--text-muted)",
                fontSize: 13,
              }}
            >
              {t("auth.register.createdBody")}
            </p>
            <button
              type="button"
              className="button-primary"
              onClick={() =>
                navigate(`/login${search}`, { replace: true })
              }
            >
              {t("auth.register.goToLogin")}
            </button>
          </div>
        </div>
      </div>
    );
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
          <h1 style={{ marginBottom: 4 }}>{t("auth.register.title")}</h1>
          <p
            style={{
              marginTop: 0,
              marginBottom: 20,
              color: "var(--text-muted)",
              fontSize: 13,
            }}
          >
            {t("auth.register.subtitle")}
          </p>

          <form
            onSubmit={handleSubmit}
            style={{ display: "flex", flexDirection: "column", gap: 14 }}
          >
            <label
              style={{ display: "flex", flexDirection: "column", gap: 4 }}
            >
              <span style={{ fontSize: 13 }}>{t("auth.register.email")}</span>
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
              <span style={{ fontSize: 13 }}>{t("auth.register.password")}</span>
              <input
                type="password"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>

            <label
              style={{ display: "flex", flexDirection: "column", gap: 4 }}
            >
              <span style={{ fontSize: 13 }}>
                {t("auth.register.confirmPassword")}
              </span>
              <input
                type="password"
                required
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
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
              {submitting
                ? t("auth.register.submitting")
                : t("auth.register.submit")}
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
            <Link to={`/login${search}`}>{t("auth.register.haveAccount")}</Link>
          </div>
        </div>
      </div>
    </div>
  );
}