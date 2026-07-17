import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useConnections, useConnectorTypes } from "../../hooks/useConnections";
import { ConnectionCard } from "./ConnectionCard";
import { ConnectionFormDialog } from "./ConnectionFormDialog";
import { Icon } from "../ui/Icon";
import { HelpIcon } from "../ui/Tooltip";

export function IntegrationsPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { data: types } = useConnectorTypes();
  const { data: connections, isLoading } = useConnections(projectId);
  const [formOpen, setFormOpen] = useState(false);

  return (
    <section className="settings-card integrations-panel">
      <div className="settings-card-head">
        <h2>
          <Icon name="plug" size={16} />
          {t("integrations.heading")}
          <HelpIcon content={t("integrations.hint")} side="right" />
        </h2>
        <p className="field-hint">{t("integrations.hint")}</p>
      </div>

      {isLoading && <p className="field-hint">{t("common.loading")}</p>}

      {connections && connections.length === 0 && (
        <p className="field-hint">{t("integrations.noConnections")}</p>
      )}

      <ul className="integrations-list">
        {connections?.map((conn) => (
          <ConnectionCard key={conn.id} connection={conn} projectId={projectId} />
        ))}
      </ul>

      <div className="settings-save-row">
        <button
          type="button"
          className="button-primary"
          onClick={() => setFormOpen(true)}
        >
          <Icon name="plus" size={14} />
          {t("integrations.addButton")}
        </button>
      </div>

      {formOpen && types && (
        <ConnectionFormDialog
          projectId={projectId}
          connectorTypes={types}
          onClose={() => setFormOpen(false)}
        />
      )}
    </section>
  );
}
