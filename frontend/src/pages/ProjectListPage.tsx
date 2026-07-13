import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { projectsApi } from "../api/projects";
import type { Project } from "../api/types";
import { Icon } from "../components/ui/Icon";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { KebabMenu } from "../components/ui/KebabMenu";
import { SkeletonList } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import {
  useCreateProject,
  useDeleteProject,
  useImportProject,
  useProjects,
} from "../hooks/useProjects";
import { translateApiError } from "../i18n/eventText";

export function ProjectListPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const { data: projects, isLoading, error } = useProjects();
  const createProject = useCreateProject();
  const importProject = useImportProject();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleCreate() {
    if (!name.trim()) return;
    createProject.mutate(
      { name, description: description || null },
      {
        onSuccess: () => {
          toast(t("projects.createdToast", { name: name.trim() }));
          setName("");
          setDescription("");
          setCreating(false);
        },
      },
    );
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

  const isEmpty = projects?.length === 0;

  const createForm = (
    <div className="project-create-form">
      <h2>{t("projects.newProjectHeading")}</h2>
      <input
        autoFocus
        placeholder={t("projects.namePlaceholder")}
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") handleCreate();
          if (e.key === "Escape") setCreating(false);
        }}
      />
      <input
        placeholder={t("projects.descriptionPlaceholder")}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") handleCreate();
          if (e.key === "Escape") setCreating(false);
        }}
      />
      <div className="project-create-actions">
        <button
          type="button"
          className="button-primary"
          onClick={handleCreate}
          disabled={!name.trim() || createProject.isPending}
        >
          {t("projects.createButton")}
        </button>
        <button type="button" className="button-ghost" onClick={() => setCreating(false)}>
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );

  return (
    <div className="project-list-page">
      <div className="project-list-header">
        <h1>{t("projects.title")}</h1>
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
      </div>

      {error && <p className="error-text">{translateApiError(error, t)}</p>}
      {importProject.isError && (
        <p className="error-text">{translateApiError(importProject.error, t)}</p>
      )}

      {creating && createForm}

      {isLoading && <SkeletonList rows={3} />}

      <div className="project-list">
        {projects?.map((project) => (
          <ProjectCard
            key={project.id}
            project={project}
            onExport={() => void handleExport(project)}
          />
        ))}
      </div>

      {isEmpty && !creating && (
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
              {t("projects.newProjectButton")}
            </button>
            <button type="button" onClick={() => fileInputRef.current?.click()}>
              {t("projects.importProject")}
            </button>
          </div>
        </div>
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
          {t("projects.entitiesCount", { count: project.entity_count })}
          {" · "}
          {t("projects.edgesCount", { count: project.edge_count })}
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
