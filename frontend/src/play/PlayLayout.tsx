import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useParams } from "react-router-dom";

import { playApi } from "../api/play";
import type { PlaySession } from "../api/types";
import { PlaySessionProvider } from "./PlaySessionContext";

type Status = "loading" | "error" | "ready";

/** The player shell: exchanges the URL token for a session cookie, then frames
 * the revealed cards and board. Rendered outside the DM Layout — no sidebar,
 * no project switcher, none of the DM tools. */
export function PlayLayout() {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const [status, setStatus] = useState<Status>("loading");
  const [session, setSession] = useState<PlaySession | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    let cancelled = false;
    setStatus("loading");
    playApi
      .startSession(token)
      .then((s) => {
        if (cancelled) return;
        setSession(s);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "loading") {
    return (
      <div className="play-splash">
        <span className="spinner" aria-hidden="true" />
        <p>{t("play.loading")}</p>
      </div>
    );
  }

  if (status === "error" || session === null) {
    return (
      <div className="play-splash">
        <h1>{t("play.linkInvalidTitle")}</h1>
        <p>{t("play.linkInvalidBody")}</p>
      </div>
    );
  }

  return (
    <PlaySessionProvider value={session}>
      <div className="play-shell">
        <header className="play-header">
          <div className="play-header-titles">
            <span className="play-project">{session.project_name}</span>
            <span className="play-player">{session.name}</span>
          </div>
          <nav className="play-nav">
            <NavLink to={`/play/${token}`} end>
              {t("play.tabCards")}
            </NavLink>
            <NavLink to={`/play/${token}/board`}>{t("play.tabBoard")}</NavLink>
          </nav>
        </header>
        <main className="play-main">
          <Outlet />
        </main>
      </div>
    </PlaySessionProvider>
  );
}
