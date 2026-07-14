import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useBlocker, useParams } from "react-router-dom";

import { KnowledgeBasePanel } from "../components/knowledge/KnowledgeBasePanel";
import { TokenUsagePanel } from "../components/usage/TokenUsagePanel";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { useProject, useReindexProject, useUpdateProject } from "../hooks/useProjects";
import { translateApiError } from "../i18n/eventText";

/** Project-level agent setup: DM style/format preferences that get blended
 * into every system prompt (assistant chat + lore generation). The project's
 * knowledge base (uploaded reference documents) lives on this same page. */
export function ProjectSettingsPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const { projectId } = useParams<{ projectId: string }>();
  const { data: project, isLoading } = useProject(projectId);
  const updateProject = useUpdateProject(projectId!);
  const reindexProject = useReindexProject(projectId!);

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

            {/* The card heading is the label — repeating it above the
                textarea just duplicated the text. */}
            <textarea
              rows={6}
              aria-label={t("projectSettings.instructionsLabel")}
              placeholder={t("projectSettings.instructionsPlaceholder")}
              value={agentInstructions}
              onChange={(e) => setAgentInstructions(e.target.value)}
            />
          </section>

          <section className="settings-card">
            <div className="settings-card-head">
              <h2>{t("projectSettings.maintenanceHeading")}</h2>
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
          </section>
        </div>

        <div className="project-settings-column">
          <KnowledgeBasePanel projectId={projectId!} />
          <TokenUsagePanel projectId={projectId!} />
        </div>
      </div>

      {/* Save applies to the two general cards above — pinned to the bottom
          so it's always reachable and clearly page-level. */}
      <div className="settings-actions">
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
        {isDirty && (
          <span className="dirty-hint">{t("projectSettings.unsavedChanges")}</span>
        )}
        {updateProject.isError && (
          <span className="error-text">
            {translateApiError(updateProject.error, t)}
          </span>
        )}
      </div>

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
