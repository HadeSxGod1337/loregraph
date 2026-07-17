import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useMatch } from "react-router-dom";

import { Icon, type IconName } from "../ui/Icon";
import { PreferencesPopover } from "./PreferencesPopover";
import { ProjectSwitcher } from "./ProjectSwitcher";

const NAV_ITEMS: { to: string; icon: IconName; labelKey: string; end?: boolean }[] = [
  { to: "entities", icon: "layers", labelKey: "nav.entities", end: true },
  { to: "graph", icon: "network", labelKey: "nav.graph" },
  { to: "assistant", icon: "sparkles", labelKey: "nav.assistant" },
  { to: "settings", icon: "settings", labelKey: "nav.settings" },
  { to: "help", icon: "help", labelKey: "nav.help" },
];

const COLLAPSE_STORAGE_KEY = "loregraph:sidebarCollapsed";

/** Replaces the old horizontal NavBar: a collapsible rail so navigation
 * scales to future sections without stretching a top bar sideways. Project
 * switching, theme/preset/language now live here too instead of three
 * separate NavBar controls. */
export function Sidebar() {
  const { t } = useTranslation();
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1",
  );

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  }

  return (
    <aside className={"sidebar" + (collapsed ? " collapsed" : "")}>
      <NavLink to="/" end className="sidebar-brand">
        <span className="sidebar-brand-mark">L</span>
        {!collapsed && <span className="sidebar-brand-word">Loregraph</span>}
      </NavLink>

      {projectId && <ProjectSwitcher projectId={projectId} collapsed={collapsed} />}

      {projectId && (
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={`/projects/${projectId}/${item.to}`}
              end={item.end}
              className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}
              title={collapsed ? t(item.labelKey) : undefined}
            >
              <Icon name={item.icon} size={17} className="sidebar-nav-icon" />
              {!collapsed && <span className="sidebar-nav-label">{t(item.labelKey)}</span>}
            </NavLink>
          ))}
        </nav>
      )}

      <div className="sidebar-spacer" />

      <div className="sidebar-foot">
        <PreferencesPopover collapsed={collapsed} />
        <button type="button" className="sidebar-collapse-btn" onClick={toggleCollapsed}>
          <Icon name="chevron-down" size={16} className="sidebar-collapse-icon" />
          {!collapsed && <span>{t("sidebar.collapse")}</span>}
        </button>
      </div>
    </aside>
  );
}
