import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useMatch } from "react-router-dom";

import { useRememberLastProject } from "../../hooks/useLastProject";
import { useProject } from "../../hooks/useProjects";
import { Sidebar } from "./Sidebar";

const SECTION_LABEL_KEYS: Record<string, string> = {
  entities: "nav.entities",
  graph: "nav.graph",
  assistant: "nav.assistant",
  integrations: "nav.integrations",
  settings: "nav.projectSettings",
};

export function Layout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;
  const section = match?.params["*"]?.split("/")[0];
  const { data: project } = useProject(projectId);
  // One place records the open project; "/" reads it back for "Continue".
  useRememberLastProject();
  const sectionLabelKey = section ? SECTION_LABEL_KEYS[section] : undefined;

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        {projectId && (
          <header className="app-topbar">
            {project && <span className="app-topbar-project">{project.name}</span>}
            {project && sectionLabelKey && <span className="app-topbar-sep">›</span>}
            {sectionLabelKey && (
              <span className="app-topbar-current">{t(sectionLabelKey)}</span>
            )}
          </header>
        )}
        <main className="layout-content">{children}</main>
      </div>
    </div>
  );
}
