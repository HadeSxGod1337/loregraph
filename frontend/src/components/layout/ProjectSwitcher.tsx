import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useDismiss } from "../../hooks/useDismiss";
import { useProjects } from "../../hooks/useProjects";
import { Icon } from "../ui/Icon";

interface ProjectSwitcherProps {
  projectId: string;
  collapsed: boolean;
}

/** Lets the user jump straight to another project without going back through
 * "/" first — the previous NavBar had no such affordance at all. */
export function ProjectSwitcher({ projectId, collapsed }: ProjectSwitcherProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: projects } = useProjects();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  useDismiss(open, rootRef, () => setOpen(false));

  const current = projects?.find((p) => p.id === projectId);

  function goToProject(id: string) {
    setOpen(false);
    if (id !== projectId) navigate(`/projects/${id}/entities`);
  }

  return (
    <div className="sidebar-switcher-wrap" ref={rootRef}>
      <button
        type="button"
        className="sidebar-switcher-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        title={collapsed ? (current?.name ?? undefined) : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="folder" size={16} className="sidebar-switcher-icon" />
        {!collapsed && (
          <span className="sidebar-switcher-label">
            <span className="sidebar-switcher-eyebrow">{t("sidebar.project")}</span>
            <span className="sidebar-switcher-name">{current?.name ?? "…"}</span>
          </span>
        )}
        {!collapsed && <Icon name="chevron-down" size={14} className="sidebar-switcher-chev" />}
      </button>

      {open && (
        <div className="sidebar-popover" role="menu">
          {(projects ?? []).map((p) => (
            <button
              key={p.id}
              type="button"
              role="menuitem"
              className={"sidebar-project-row" + (p.id === projectId ? " active" : "")}
              onClick={() => goToProject(p.id)}
            >
              <span className="sidebar-project-dot">{p.name.charAt(0).toUpperCase()}</span>
              <span className="sidebar-project-name">{p.name}</span>
              {p.id === projectId && <Icon name="check" size={14} className="sidebar-project-check" />}
            </button>
          ))}
          <div className="sidebar-popover-divider" />
          <button
            type="button"
            role="menuitem"
            className="sidebar-popover-action"
            onClick={() => {
              setOpen(false);
              navigate("/");
            }}
          >
            <Icon name="arrow-left" size={14} />
            {t("sidebar.allProjects")}
          </button>
        </div>
      )}
    </div>
  );
}
