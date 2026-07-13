import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { KnowledgeBasePanel } from "../components/knowledge/KnowledgeBasePanel";
import { useProject, useUpdateProject } from "../hooks/useProjects";
import { translateApiError } from "../i18n/eventText";

/** Project-level agent setup: DM style/format preferences that get blended
 * into every system prompt (assistant chat + lore generation). The project's
 * knowledge base (uploaded reference documents) lives on this same page. */
export function ProjectSettingsPage() {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();
  const { data: project, isLoading } = useProject(projectId);
  const updateProject = useUpdateProject(projectId!);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [agentInstructions, setAgentInstructions] = useState("");

  useEffect(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description ?? "");
      setAgentInstructions(project.agent_instructions ?? "");
    }
  }, [project]);

  function handleSave() {
    if (!name.trim()) return;
    updateProject.mutate({
      name,
      description: description || null,
      agent_instructions: agentInstructions || null,
    });
  }

  if (isLoading || !project) return <p>{t("common.loading")}</p>;

  return (
    <div className="project-settings-page">
      <h1>{t("projectSettings.heading")}</h1>

      <div className="project-settings-columns">
        <div className="project-settings-column">
          <section className="settings-card">
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
          </section>

          <section className="settings-card">
            <div className="settings-card-head">
              <h2>{t("projectSettings.agentHeading")}</h2>
              <p className="field-hint">{t("projectSettings.instructionsHint")}</p>
            </div>

            <label>
              {t("projectSettings.instructionsLabel")}
              <textarea
                rows={6}
                placeholder={t("projectSettings.instructionsPlaceholder")}
                value={agentInstructions}
                onChange={(e) => setAgentInstructions(e.target.value)}
              />
            </label>
          </section>

          <div className="settings-save-row">
            <button
              type="button"
              className="button-primary"
              disabled={!name.trim()}
              onClick={handleSave}
            >
              {updateProject.isPending
                ? t("projectSettings.saving")
                : t("projectSettings.saveButton")}
            </button>
            {updateProject.isSuccess && (
              <span className="settings-save-status">
                {t("projectSettings.saved")}
              </span>
            )}
            {updateProject.isError && (
              <span className="error-text">
                {translateApiError(updateProject.error, t)}
              </span>
            )}
          </div>
        </div>

        <div className="project-settings-column">
          <KnowledgeBasePanel projectId={projectId!} />
        </div>
      </div>
    </div>
  );
}
