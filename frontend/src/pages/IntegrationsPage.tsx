import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { IntegrationsPanel } from "../components/integrations/IntegrationsPanel";
import { Icon } from "../components/ui/Icon";

/** Integrations used to be one tab inside project settings, two clicks and a
 * side-nav away from anywhere. They are a place you go to work — importing a
 * party, pushing a session to a vault — not a setting you configure once, so
 * they sit in the left rail next to the graph and the assistant. */
export function IntegrationsPage() {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();

  return (
    <div className="project-settings-page integrations-page">
      <h1>
        <Icon name="plug" size={20} />
        {t("integrations.heading")}
      </h1>
      <IntegrationsPanel projectId={projectId!} />
    </div>
  );
}
