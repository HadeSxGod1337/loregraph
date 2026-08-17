import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { projectsApi } from "../api/projects";
import type { Project } from "../api/types";
import { CreateProjectDialog } from "../components/projects/CreateProjectDialog";
import { Icon } from "../components/ui/Icon";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { KebabMenu } from "../components/ui/KebabMenu";
import { SkeletonList } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import { useDeleteProject, useImportProject, useProjects } from "../hooks/useProjects";
import { useLastProject } from "../hooks/useLastProject";
import { translateApiError } from "../i18n/eventText";
import { filterProjects } from "./projectFilter";

export function ProjectListPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const { data: projects, isLoading, error } = useProjects();
  const importProject = useImportProject();
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleCreated(name: string) {
    toast(t("projects.createdToast", { name }));
    setCreating(false);
  }

  async function handleExport(project: Project) {
    const data = await projectsApi.export(project.id);
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${project.name.replace(/[^\w.-]+/g, "_")}.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast(t("projects.exportedToast", { name: project.name }));
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const text = await file.text();
    importProject.mutate(JSON.parse(text), {
      onSuccess: () => toast(t("projects.importedToast")),
    });
  }

  const lastProjectId = useLastProject();
  // The world you were in last is the one you almost always want again; it
  // gets its own card instead of being one row among eleven identical ones.
  const continueProject = projects?.find((p) => p.id === lastProjectId);
  const rest = useMemo(
    () => filterProjects(projects ?? [], continueProject?.id, query),
    [projects, continueProject, query],
  );

  const isEmpty = projects?.length === 0;

  return (
    <div className="project-list-page">
      <header className="project-list-header">
        <div className="project-list-title">
          <h1>{t("projects.title")}</h1>
          {projects && projects.length > 0 && (
            <p className="field-hint">
              {t("projects.projectsCount", { count: projects.length })}
              {" · "}
              {t("projects.entitiesCount", {
                count: projects.reduce((sum, p) => sum + p.entity_count, 0),
              })}
            </p>
          )}
        </div>
        <div className="page-header-actions">
          <button type="button" onClick={() => fileInputRef.current?.click()}>
            <Icon name="download" />
            {t("projects.importProject")}
          </button>
          <button
            type="button"
            className="button-primary"
            onClick={() => setCreating(true)}
          >
            <Icon name="plus" />
            {t("projects.newProjectButton")}
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          onChange={(e) => void handleImportFile(e)}
          style={{ display: "none" }}
        />
      </header>

      {error && <p className="error-text">{translateApiError(error, t)}</p>}
      {importProject.isError && (
        <p className="error-text">{translateApiError(importProject.error, t)}</p>
      )}

      {isLoading && <SkeletonList rows={3} />}

      {continueProject && (
        <Link
          to={`/projects/${continueProject.id}/entities`}
          className="project-continue"
        >
          <span className="project-continue-mark" aria-hidden="true">
            {continueProject.name.slice(0, 1).toUpperCase()}
          </span>
          <span className="project-continue-body">
            <span className="project-continue-eyebrow">
              {t("projects.lastProjectLabel")}
            </span>
            <span className="project-continue-name">{continueProject.name}</span>
            <span className="project-continue-stats">
              {t("projects.entitiesCount", { count: continueProject.entity_count })}
              {" · "}
              {t("projects.edgesCount", { count: continueProject.edge_count })}
            </span>
          </span>
          <span className="project-continue-open">
            {t("projects.openButton")}
            <Icon name="chevron-right" size={15} />
          </span>
        </Link>
      )}

      {projects && projects.length > 4 && (
        <div className="project-list-filter">
          <Icon name="search" size={15} />
          <input
            value={query}
            placeholder={t("projects.filterPlaceholder")}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      )}

      {rest.length > 0 && (
        <div className="project-list">
          {rest.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onExport={() => void handleExport(project)}
            />
          ))}
        </div>
      )}

      {projects && rest.length === 0 && query.trim() !== "" && (
        <p className="field-hint">{t("projects.noMatches", { query: query.trim() })}</p>
      )}

      {isEmpty && (
        <div className="empty-state">
          <p>
            <b>{t("projects.noProjects")}</b>
          </p>
          <p>{t("projects.emptyBody")}</p>
          <div className="empty-state-actions">
            <button
              type="button"
              className="button-primary"
              onClick={() => setCreating(true)}
            >
              <Icon name="plus" />
              {t("projects.emptyCreateButton")}
            </button>
            <button type="button" onClick={() => fileInputRef.current?.click()}>
              {t("projects.importProject")}
            </button>
          </div>
        </div>
      )}

      {creating && (
        <CreateProjectDialog
          onClose={() => setCreating(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}

function ProjectCard({
  project,
  onExport,
}: {
  project: Project;
  onExport: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const deleteProject = useDeleteProject();
  const [confirming, setConfirming] = useState(false);

  function handleDeleteConfirmed() {
    deleteProject.mutate(project.id, {
      onSuccess: () => toast(t("projects.deletedToast")),
    });
  }

  return (
    <div className="project-card">
      <Link to={`/projects/${project.id}/entities`} className="project-card-link">
        <h3>{project.name}</h3>
        {project.description && <p>{project.description}</p>}
        <p className="project-card-stats">
          <span className="project-chip">
            {t("projects.entitiesCount", { count: project.entity_count })}
          </span>
          <span className="project-chip">
            {t("projects.edgesCount", { count: project.edge_count })}
          </span>
        </p>
      </Link>
      <div className="project-card-actions">
        <KebabMenu
          label={t("projects.menuLabel")}
          items={[
            { label: t("projects.exportButton"), onClick: onExport },
            {
              label: t("projects.deleteButton"),
              onClick: () => setConfirming(true),
              danger: true,
            },
          ]}
        />
      </div>
      {confirming && (
        <ConfirmDialog
          title={t("projects.deleteConfirmTitle")}
          body={t("projects.deleteConfirmBody", { name: project.name })}
          confirmLabel={t("projects.confirmDeleteButton")}
          requireText={project.name}
          requirePlaceholder={t("projects.deleteConfirmPlaceholder", {
            name: project.name,
          })}
          busy={deleteProject.isPending}
          onConfirm={handleDeleteConfirmed}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
