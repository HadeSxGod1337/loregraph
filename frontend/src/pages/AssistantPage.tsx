import { useParams } from "react-router-dom";

import { AssistantPanel } from "../components/assistant/AssistantPanel";

/** Full-page home for the assistant. The same panel is embedded in the graph
 * view as a drawer — this page is the roomier place to review big batches. */
export function AssistantPage() {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <div className="assistant-page">
      <div className="assistant-header">
        <h1>AI Assistant</h1>
        <p className="assistant-hint">
          Describe a piece of your world — the assistant drafts entities and
          the relationship web between them; nothing becomes canon until you
          approve it.
        </p>
      </div>
      <AssistantPanel projectId={projectId!} />
    </div>
  );
}
