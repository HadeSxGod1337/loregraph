import { Link, NavLink } from "react-router-dom";

import { useProject } from "../../hooks/useProjects";

export function ProjectHeader({ projectId }: { projectId: string }) {
  const { data: project } = useProject(projectId);

  return (
    <div className="project-header">
      <Link to="/" className="project-header-back">
        ← All projects
      </Link>
      {project && <span className="project-header-name">{project.name}</span>}
      <div className="project-header-links">
        <NavLink to={`/projects/${projectId}/entities`} end>
          Entities
        </NavLink>
        <NavLink to={`/projects/${projectId}/graph`}>Graph</NavLink>
      </div>
    </div>
  );
}
