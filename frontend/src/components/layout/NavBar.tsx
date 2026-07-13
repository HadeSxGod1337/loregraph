import { useTranslation } from "react-i18next";
import { Link, NavLink, useMatch } from "react-router-dom";

import { useProject } from "../../hooks/useProjects";
import { Icon } from "../ui/Icon";
import { LanguagePicker } from "./LanguagePicker";
import { ThemePicker } from "./ThemePicker";

export function NavBar() {
  const { t } = useTranslation();
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;
  const { data: project } = useProject(projectId);

  return (
    <nav className="navbar">
      <NavLink to="/" end className="navbar-brand">
        Loregraph
      </NavLink>
      {projectId && (
        <>
          <Link to="/" className="navbar-project-back link-button">
            {t("nav.allProjects")}
          </Link>
          {project && <span className="navbar-project-name">{project.name}</span>}
          <div className="navbar-links">
            <NavLink to={`/projects/${projectId}/entities`} end>
              {t("nav.entities")}
            </NavLink>
            <NavLink to={`/projects/${projectId}/graph`}>{t("nav.graph")}</NavLink>
            <NavLink to={`/projects/${projectId}/assistant`}>
              {t("nav.assistant")}
            </NavLink>
            <NavLink to={`/projects/${projectId}/settings`}>
              <Icon name="settings" size={13} /> {t("nav.settings")}
            </NavLink>
          </div>
        </>
      )}
      <div className="navbar-controls">
        <LanguagePicker />
        <ThemePicker />
      </div>
    </nav>
  );
}
