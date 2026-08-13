import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation, useMatch } from "react-router-dom";

import { privateNavItems } from "@loregraph/private-ui";
import { useLastProject } from "../../hooks/useLastProject";
import { useProjects } from "../../hooks/useProjects";
import { useUpdateStatus } from "../../hooks/useUpdates";
import { Icon, type IconName } from "../ui/Icon";
import { CommandPalette } from "./CommandPalette";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { SidebarStatus } from "./SidebarStatus";
import { ThemeToggle } from "./ThemeToggle";

const PROJECT_NAV: { to: string; icon: IconName; labelKey: string; end?: boolean }[] = [
  { to: "entities", icon: "layers", labelKey: "nav.entities", end: true },
  { to: "graph", icon: "network", labelKey: "nav.graph" },
  { to: "assistant", icon: "sparkles", labelKey: "nav.assistant" },
  { to: "integrations", icon: "plug", labelKey: "nav.integrations" },
  { to: "settings", icon: "folder", labelKey: "nav.projectSettings" },
];

const COLLAPSE_STORAGE_KEY = "loregraph:sidebarCollapsed";
/** How many projects the rail offers on "/" before the list stops being a
 * shortcut. The full set is one click away on the page itself. */
const RECENT_LIMIT = 5;

/** The rail. Two zones, always with something in it.
 *
 * Zone one is the open project (its sections); zone two is the app itself
 * (settings, help, theme). They are labelled and separated because the
 * previous single stack put "Настройки" (this project) and "Настройки ИИ"
 * (the whole installation) side by side under the same word.
 *
 * On "/" there is no project, so the project zone is replaced by recent
 * projects rather than left blank — that emptiness was the original
 * complaint. */
export function Sidebar() {
  const { t } = useTranslation();
  const match = useMatch("/projects/:projectId/*");
  const routeProjectId = match?.params.projectId;
  const { pathname } = useLocation();
  const lastProjectId = useLastProject();
  const { data: projects } = useProjects();
  // The update dot used to sit on the appearance popover; that button is
  // gone, so it moves to the section that now owns updates.
  const { data: updateStatus } = useUpdateStatus();
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1",
  );
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  }

  // Public items carry an i18n key; private items (from the optional
  // @loregraph/private-ui package, empty by default) carry a plain label —
  // normalized to `label` here so the render below doesn't care which.
  const projectItems = [
    ...PROJECT_NAV.map((item) => ({ ...item, label: t(item.labelKey) })),
    ...privateNavItems,
  ];

  const recent = (projects ?? []).slice(0, RECENT_LIMIT);

  // App settings live outside /projects, but opening them should not read as
  // leaving the world you had open — the rail keeps the project you came from
  // so getting back is one click, not a trip through the project list. "/" is
  // the exception: there you are choosing a project, and recents are the point.
  // The stored id is checked against the real list so a deleted project does
  // not leave a dead zone behind (undefined = still loading, trust it for now).
  const carriedProjectId =
    pathname === "/" ||
    !lastProjectId ||
    (projects !== undefined && !projects.some((p) => p.id === lastProjectId))
      ? undefined
      : lastProjectId;
  const projectId = routeProjectId ?? carriedProjectId;

  return (
    <aside className={"sidebar" + (collapsed ? " collapsed" : "")}>
      <div className="sidebar-brand-row">
        {/* Collapsed, the brand steps aside entirely: a 26 px mark and a 26 px
            control do not both fit a 60 px rail, and of the two only one is
            something you click on purpose. The control keeps its place at the
            top in both states rather than moving to the footer. */}
        {!collapsed && (
          <NavLink to="/" end className="sidebar-brand">
            <span className="sidebar-brand-mark">L</span>
            <span className="sidebar-brand-word">Loregraph</span>
          </NavLink>
        )}
        <CollapseButton collapsed={collapsed} onToggle={toggleCollapsed} />
      </div>

      <button
        type="button"
        className="sidebar-search"
        onClick={() => setPaletteOpen(true)}
        title={collapsed ? t("palette.title") : undefined}
      >
        <Icon name="search" size={14} />
        {!collapsed && <span>{t("palette.title")}</span>}
      </button>

      {projectId && <ProjectSwitcher projectId={projectId} collapsed={collapsed} />}

      {projectId ? (
        <>
          {!collapsed && <div className="sidebar-group-label">{t("sidebar.project")}</div>}
          <nav className="sidebar-nav">
            {projectItems.map((item) => (
              <NavLink
                key={item.to}
                to={`/projects/${projectId}/${item.to}`}
                end={item.end}
                className={({ isActive }) =>
                  "sidebar-nav-item" + (isActive ? " active" : "")
                }
                title={collapsed ? item.label : undefined}
              >
                <Icon name={item.icon} size={17} className="sidebar-nav-icon" />
                {!collapsed && <span className="sidebar-nav-label">{item.label}</span>}
              </NavLink>
            ))}
          </nav>
        </>
      ) : (
        <>
          {!collapsed && <div className="sidebar-group-label">{t("sidebar.recent")}</div>}
          <nav className="sidebar-nav">
            {recent.map((project) => (
              <NavLink
                key={project.id}
                to={`/projects/${project.id}/entities`}
                className="sidebar-nav-item"
                title={collapsed ? project.name : undefined}
              >
                <span className="sidebar-recent-mark" aria-hidden="true">
                  {project.name.slice(0, 1).toUpperCase()}
                </span>
                {!collapsed && (
                  <span className="sidebar-nav-label">{project.name}</span>
                )}
              </NavLink>
            ))}
          </nav>
        </>
      )}

      <div className="sidebar-spacer" />

      <SidebarStatus collapsed={collapsed} />

      <div className="sidebar-zone-divider" />

      {!collapsed && <div className="sidebar-group-label">{t("sidebar.app")}</div>}
      <div className="sidebar-foot">
        <NavLink
          to="/settings"
          className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}
          title={collapsed ? t("nav.appSettings") : undefined}
        >
          <Icon name="settings" size={17} className="sidebar-nav-icon" />
          {!collapsed && <span className="sidebar-nav-label">{t("nav.appSettings")}</span>}
          {updateStatus?.update_available && (
            <span
              className="sidebar-nav-badge"
              title={t("updates.available", { version: updateStatus.latest_version })}
            />
          )}
        </NavLink>
        {/* Help is written against a project (its entities, its graph), so it
            only appears once there is one. */}
        {projectId && (
          <NavLink
            to={`/projects/${projectId}/help`}
            className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}
            title={collapsed ? t("nav.help") : undefined}
          >
            <Icon name="help" size={17} className="sidebar-nav-icon" />
            {!collapsed && <span className="sidebar-nav-label">{t("nav.help")}</span>}
          </NavLink>
        )}
        <ThemeToggle collapsed={collapsed} />
      </div>

      <CommandPalette
        projectId={projectId}
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
      />
    </aside>
  );
}

function CollapseButton({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const label = t(collapsed ? "sidebar.expand" : "sidebar.collapse");
  return (
    <button
      type="button"
      className="sidebar-collapse-btn"
      onClick={onToggle}
      title={label}
      aria-label={label}
      aria-expanded={!collapsed}
    >
      <Icon name="panel-left" size={17} />
    </button>
  );
}
