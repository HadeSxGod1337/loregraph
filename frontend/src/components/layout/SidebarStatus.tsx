import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAgentConfig } from "../../hooks/useAgent";
import { useAppSettings, useReindexStatus } from "../../hooks/useAppSettings";

interface Props {
  collapsed: boolean;
}

type Tone = "ok" | "warn" | "busy";

/** What the AI is doing right now, pinned to the bottom of the rail.
 *
 * Before this, the only way to find out that no key was configured was to
 * open the assistant and read an onboarding card, and a running reindex —
 * during which retrieval is incomplete — was invisible everywhere except the
 * settings page you had to already be on. */
export function SidebarStatus({ collapsed }: Props) {
  const { t } = useTranslation();
  const { data: config } = useAgentConfig();
  const { data: settings } = useAppSettings();
  // Poll only while a rebuild is actually running (see useReindexStatus).
  const { data: polled } = useReindexStatus(settings?.reindex.state === "running");
  const reindex = polled ?? settings?.reindex;

  if (!config) return null;

  const tone: Tone = !config.llm_configured
    ? "warn"
    : reindex?.state === "running"
      ? "busy"
      : "ok";

  const value =
    tone === "warn"
      ? t("sidebarStatus.noKey")
      : tone === "busy"
        ? t("sidebarStatus.reindexing", {
            done: reindex?.done_projects ?? 0,
            total: reindex?.total_projects ?? 0,
          })
        : config.model_generation;

  const title = tone === "warn" ? t("sidebarStatus.noKeyTitle") : config.llm_provider;

  return (
    <Link
      to={tone === "busy" ? "/settings?section=embeddings" : "/settings"}
      className={"sidebar-status tone-" + tone}
      title={collapsed ? `${title} · ${value}` : undefined}
    >
      <span className="sidebar-status-dot" aria-hidden="true" />
      {!collapsed && (
        <span className="sidebar-status-text">
          <span className="sidebar-status-title">{title}</span>
          <span className="sidebar-status-value">{value}</span>
        </span>
      )}
    </Link>
  );
}
