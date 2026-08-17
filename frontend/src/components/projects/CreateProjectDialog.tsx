import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useCreateProject } from "../../hooks/useProjects";
import { translateApiError } from "../../i18n/eventText";

/** Modal "new project" flow. Replaces the old inline form that used to push
 * the whole project list down the page every time it opened — a dialog
 * keeps the list stable underneath it. */
export function CreateProjectDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const { t } = useTranslation();
  const createProject = useCreateProject();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function handleCreate() {
    const trimmed = name.trim();
    if (!trimmed || createProject.isPending) return;
    createProject.mutate(
      { name: trimmed, description: description.trim() || null },
      { onSuccess: () => onCreated(trimmed) },
    );
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t("projects.newProjectHeading")}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{t("projects.newProjectHeading")}</h2>

        <form
          className="create-project-form"
          onSubmit={(e) => {
            e.preventDefault();
            handleCreate();
          }}
        >
          <input
            autoFocus
            placeholder={t("projects.namePlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
            }}
          />
          <input
            placeholder={t("projects.descriptionPlaceholder")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
            }}
          />

          {createProject.isError && (
            <p className="error-text">
              {translateApiError(createProject.error, t)}
            </p>
          )}

          <div className="dialog-actions">
            <button type="button" className="button-ghost" onClick={onClose}>
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              className="button-primary"
              disabled={!name.trim() || createProject.isPending}
            >
              {t("projects.createButton")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
