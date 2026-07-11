import { Link, NavLink, useMatch } from "react-router-dom";

import { useProject } from "../../hooks/useProjects";
import { ThemePicker } from "./ThemePicker";

export function NavBar() {
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
          <Link to="/" className="navbar-project-back">
            ← All projects
          </Link>
          {project && <span className="navbar-project-name">{project.name}</span>}
          <div className="navbar-links">
            <NavLink to={`/projects/${projectId}/entities`} end>
              Entities
            </NavLink>
            <NavLink to={`/projects/${projectId}/graph`}>Graph</NavLink>
            <NavLink to={`/projects/${projectId}/assistant`}>AI Assistant</NavLink>
          </div>
        </>
      )}
      <ThemePicker />
    </nav>
  );
}
