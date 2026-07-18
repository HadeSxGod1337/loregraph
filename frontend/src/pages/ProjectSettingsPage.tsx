import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useBlocker, useNavigate, useParams } from "react-router-dom";

import { IntegrationsPanel } from "../components/integrations/IntegrationsPanel";
import { KnowledgeBasePanel } from "../components/knowledge/KnowledgeBasePanel";
import { TokenUsagePanel } from "../components/usage/TokenUsagePanel";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { Icon, type IconName } from "../components/ui/Icon";
import { useToast } from "../components/ui/Toast";
import {
  useDeleteProject,
  useProject,
  useReindexProject,
  useUpdateProject,
} from "../hooks/useProjects";
import { translateApiError } from "../i18n/eventText";

type SettingsSection = "general" | "knowledge" | "integrations" | "usage" | "danger";

const NAV_SECTIONS: { id: SettingsSection; icon: IconName; labelKey: string }[] = [
  { id: "general", icon: "settings", labelKey: "projectSettings.navGeneral" },
  { id: "knowledge", icon: "folder", labelKey: "projectSettings.navKnowledge" },
  { id: "integrations", icon: "plug", labelKey: "projectSettings.navIntegrations" },
  { id: "usage", icon: "bar-chart", labelKey: "projectSettings.navUsage" },
];

/** Project-level agent setup: DM style/format preferences that get blended
 * into every system prompt (assistant chat + lore generation). The project's
 * knowledge base (uploaded reference documents) lives on this same page. */
export function ProjectSettingsPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const { data: project, isLoading } = useProject(projectId);
  const updateProject = useUpdateProject(projectId!);
  const reindexProject = useReindexProject(projectId!);
  const deleteProject = useDeleteProject();

  const [section, setSection] = useState<SettingsSection>("general");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [agentInstructions, setAgentInstructions] = useState("");
  const [deleteConfirming, setDeleteConfirming] = useState(false);

  useEffect(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description ?? "");
      setAgentInstructions(project.agent_instructions ?? "");
    }
  }, [project]);

  const isDirty =
    project !== undefined &&
    (name !== project.name ||
      description !== (project.description ?? "") ||
      agentInstructions !== (project.agent_instructions ?? ""));

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty && currentLocation.pathname !== nextLocation.pathname,
  );

  useEffect(() => {
    if (!isDirty) return;
    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  function handleSave() {
    if (!name.trim()) return;
    updateProject.mutate(
      {
        name,
        description: description || null,
        agent_instructions: agentInstructions || null,
      },
      { onSuccess: () => toast(t("projectSettings.saved")) },
    );
  }

  function handleReindex() {
    reindexProject.mutate(undefined, {
      onSuccess: (result) =>
        toast(t("projectSettings.reindexed", { count: result.indexed })),
    });
  }

  function handleDeleteConfirmed() {
    deleteProject.mutate(projectId!, {
      onSuccess: () => {
        toast(t("projects.deletedToast"));
        navigate("/");
      },
    });
  }

  if (isLoading || !project) return <p>{t("common.loading")}</p>;

  return (
    <div className="project-settings-page">
      <h1>{t("projectSettings.heading")}</h1>

      <div className="settings-shell">
        <nav className="settings-nav">
          {NAV_SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={"settings-nav-item" + (section === item.id ? " active" : "")}
              onClick={() => setSection(item.id)}
            >
              <Icon name={item.icon} size={15} />
              {t(item.labelKey)}
            </button>
          ))}
          <div className="settings-nav-divider" />
          <button
            type="button"
            className={
              "settings-nav-item danger" + (section === "danger" ? " active" : "")
            }
            onClick={() => setSection("danger")}
          >
            <Icon name="alert" size={15} />
            {t("projectSettings.navDanger")}
          </button>
        </nav>

        <div className="settings-panel">
          {section === "general" && (
            <section className="settings-editable-group">
              <div className="settings-editable-eyebrow">
                <span className="settings-live-dot" aria-hidden="true" />
                {t("projectSettings.editableTag")}
              </div>
              <div className="settings-editable-body">
                <div className="settings-card-head">
                  <h2>{t("projectSettings.generalHeading")}</h2>
                </div>

                <label>
                  {t("projectSettings.nameLabel")}
                  <input value={name} onChange={(e) => setName(e.target.value)} />
                </label>

                <label>
                  {t("projectSettings.descriptionLabel")}
                  <input
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </label>

                <div className="settings-editable-divider" />

                <div className="settings-card-head">
                  <h2>{t("projectSettings.agentHeading")}</h2>
                  <p className="field-hint">{t("projectSettings.instructionsHint")}</p>
                </div>

                {/* The card heading is the label — repeating it above the
                    textarea just duplicated the text. */}
                <textarea
                  rows={6}
                  aria-label={t("projectSettings.instructionsLabel")}
                  placeholder={t("projectSettings.instructionsPlaceholder")}
                  value={agentInstructions}
                  onChange={(e) => setAgentInstructions(e.target.value)}
                />
              </div>

              <div className="settings-editable-foot">
                <span className={"dirty-hint" + (isDirty ? "" : " settings-saved-hint")}>
                  {isDirty
                    ? t("projectSettings.unsavedChanges")
                    : t("projectSettings.allSaved")}
                </span>
                <div className="settings-save-row">
                  {updateProject.isError && (
                    <span className="error-text">
                      {translateApiError(updateProject.error, t)}
                    </span>
                  )}
                  <button
                    type="button"
                    className="button-primary"
                    disabled={!name.trim() || !isDirty || updateProject.isPending}
                    onClick={handleSave}
                  >
                    {updateProject.isPending && <span className="spinner" aria-hidden="true" />}
                    {updateProject.isPending
                      ? t("projectSettings.saving")
                      : t("projectSettings.saveButton")}
                  </button>
                </div>
              </div>
            </section>
          )}

          {section === "knowledge" && (
            <section className="settings-card">
              <KnowledgeBasePanel projectId={projectId!} />

              <div className="reindex-row">
                <div className="reindex-copy">
                  <p className="reindex-label">{t("projectSettings.maintenanceHeading")}</p>
                  <p className="field-hint">{t("projectSettings.reindexHint")}</p>
                </div>
                <div className="settings-save-row">
                  <button
                    type="button"
                    disabled={reindexProject.isPending}
                    onClick={handleReindex}
                  >
                    {reindexProject.isPending && (
                      <span className="spinner" aria-hidden="true" />
                    )}
                    {reindexProject.isPending
                      ? t("projectSettings.reindexing")
                      : t("projectSettings.reindexButton")}
                  </button>
                  {reindexProject.isError && (
                    <span className="error-text">
                      {translateApiError(reindexProject.error, t)}
                    </span>
                  )}
                </div>
              </div>
            </section>
          )}

          {section === "integrations" && <IntegrationsPanel projectId={projectId!} />}

          {section === "usage" && <TokenUsagePanel projectId={projectId!} />}

          {section === "danger" && (
            <section className="settings-card danger-zone">
              <div className="settings-card-head">
                <h2>{t("projectSettings.dangerHeading")}</h2>
                <p className="field-hint">{t("projectSettings.dangerHint")}</p>
              </div>
              <div className="danger-zone-row">
                <div className="danger-zone-copy">
                  <p>{t("projectSettings.deleteProjectLabel")}</p>
                  <p className="field-hint">{t("projectSettings.deleteProjectHint")}</p>
                </div>
                <button
                  type="button"
                  className="button-danger"
                  onClick={() => setDeleteConfirming(true)}
                >
                  {t("projectSettings.deleteProjectLabel")}
                </button>
              </div>
            </section>
          )}
        </div>
      </div>

      {deleteConfirming && (
        <ConfirmDialog
          title={t("projects.deleteConfirmTitle")}
          body={t("projects.deleteConfirmBody", { name: project.name })}
          confirmLabel={t("projects.confirmDeleteButton")}
          requireText={project.name}
          requirePlaceholder={t("projects.deleteConfirmPlaceholder", { name: project.name })}
          busy={deleteProject.isPending}
          onConfirm={handleDeleteConfirmed}
          onCancel={() => setDeleteConfirming(false)}
        />
      )}

      {blocker.state === "blocked" && (
        <ConfirmDialog
          title={t("common.leaveTitle")}
          body={t("common.leaveBody")}
          confirmLabel={t("common.leaveButton")}
          onConfirm={() => blocker.proceed()}
          onCancel={() => blocker.reset()}
        />
      )}
    </div>
  );
}
