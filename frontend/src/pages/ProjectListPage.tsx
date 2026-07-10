import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { projectsApi } from "../api/projects";
import type { Project } from "../api/types";
import {
  useCreateProject,
  useDeleteProject,
  useImportProject,
  useProjects,
} from "../hooks/useProjects";

export function ProjectListPage() {
  const { data: projects, isLoading, error } = useProjects();
  const createProject = useCreateProject();
  const importProject = useImportProject();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleCreate() {
    if (!name.trim()) return;
    createProject.mutate(
      { name, description: description || null },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
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
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const text = await file.text();
    importProject.mutate(JSON.parse(text));
  }

  return (
    <div className="project-list-page">
      <div className="project-list-header">
        <h1>Projects</h1>
        <button type="button" onClick={() => fileInputRef.current?.click()}>
          Import project
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          onChange={(e) => void handleImportFile(e)}
          style={{ display: "none" }}
        />
      </div>

      {isLoading && <p>Loading...</p>}
      {error && <p className="error-text">{(error as Error).message}</p>}
      {importProject.isError && (
        <p className="error-text">{(importProject.error as Error).message}</p>
      )}

      <div className="project-list">
        {projects?.map((project) => (
          <ProjectCard
            key={project.id}
            project={project}
            onExport={() => void handleExport(project)}
          />
        ))}
      </div>

      {projects?.length === 0 && <p>No projects yet. Create one to get started.</p>}

      <div className="project-create-form">
        <h2>+ New Project</h2>
        <input
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button type="button" onClick={handleCreate} disabled={!name.trim()}>
          Create
        </button>
      </div>
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
  const deleteProject = useDeleteProject();
  const [confirming, setConfirming] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  return (
    <div className="project-card">
      <Link to={`/projects/${project.id}/entities`} className="project-card-link">
        <h3>{project.name}</h3>
        {project.description && <p>{project.description}</p>}
      </Link>
      <div className="project-card-actions">
        <button type="button" onClick={onExport}>
          Export
        </button>
        {confirming ? (
          <>
            <input
              placeholder={`Type "${project.name}" to confirm`}
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
            />
            <button
              type="button"
              className="button-danger"
              disabled={confirmText !== project.name}
              onClick={() => deleteProject.mutate(project.id)}
            >
              Confirm delete
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            className="button-danger"
            onClick={() => setConfirming(true)}
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
