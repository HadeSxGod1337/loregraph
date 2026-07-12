import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { AssistantPanel } from "../components/assistant/AssistantPanel";

/** Full-page home for the assistant. The same panel is embedded in the graph
 * view as a drawer — this page is the roomier place to review big batches. */
export function AssistantPage() {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <div className="assistant-page">
      <div className="assistant-header">
        <h1>{t("nav.assistant")}</h1>
        <p className="assistant-hint">{t("assistant.emptyInviteHasWorld")}</p>
      </div>
      <AssistantPanel projectId={projectId!} />
    </div>
  );
}
