import { Link, NavLink } from "react-router-dom";

import { useProject } from "../../hooks/useProjects";

interface ProjectHeaderProps {
  projectId: string;
  // Reserve space matching the detail panel's width so the nav links shift
  // left to sit beside it instead of floating over its top edge.
  reserveForPanel?: boolean;
}

export function ProjectHeader({ projectId, reserveForPanel }: ProjectHeaderProps) {
  const { data: project } = useProject(projectId);

  return (
    <div
      className={`project-header${reserveForPanel ? " project-header-reserve" : ""}`}
    >
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
