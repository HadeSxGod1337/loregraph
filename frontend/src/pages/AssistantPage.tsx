import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { AssistantPanel } from "../components/assistant/AssistantPanel";

/** Full-page home for the assistant. The same panel is embedded in the graph
 * view as a drawer — this page is the roomier place to review big batches.
 * The title renders inside AssistantPanel's own session-picker row (via
 * `heading`) rather than a separate block above it — the drawer keeps its
 * own header instead, since it also needs a close button. */
export function AssistantPage() {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <div className="assistant-page">
      <AssistantPanel projectId={projectId!} heading={t("nav.assistant")} />
    </div>
  );
}
