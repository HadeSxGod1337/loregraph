import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { KnowledgeBasePanel } from "../components/knowledge/KnowledgeBasePanel";
import { useProject, useUpdateProject } from "../hooks/useProjects";

/** Project-level agent setup: DM style/format preferences that get blended
 * into every system prompt (assistant chat + lore generation). The project's
 * knowledge base (uploaded reference documents) lives on this same page. */
export function ProjectSettingsPage() {
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

  if (isLoading || !project) return <p>Loading...</p>;

  return (
    <div className="project-settings-page">
      <h1>Настройки проекта</h1>

      <label>
        Название
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>

      <label>
        Описание
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>

      <label>
        Инструкции для ассистента
        <textarea
          rows={6}
          placeholder={
            'Например: «Пиши описания NPC от второго лица», «Всегда добавляй ' +
            'поле "крючок сюжета"», «Придерживайся мрачного, готического тона».'
          }
          value={agentInstructions}
          onChange={(e) => setAgentInstructions(e.target.value)}
        />
        <span className="field-hint">
          Свободный текст о стиле, тоне и формате — подмешивается в системный
          промпт ассистента и генерации лора для этого проекта.
        </span>
      </label>

      <button type="button" disabled={!name.trim()} onClick={handleSave}>
        {updateProject.isPending ? "Сохраняю…" : "Сохранить"}
      </button>
      {updateProject.isSuccess && <span className="field-hint">Сохранено.</span>}
      {updateProject.isError && (
        <p className="error-text">{(updateProject.error as Error).message}</p>
      )}

      <KnowledgeBasePanel projectId={projectId!} />
    </div>
  );
}
