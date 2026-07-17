import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Connection } from "../../api/types";
import {
  useDeleteConnection,
  useTestConnection,
  useUpdateConnection,
} from "../../hooks/useConnections";
import { translateApiError } from "../../i18n/eventText";
import { Checkbox } from "../ui/Checkbox";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { Icon } from "../ui/Icon";
import { KebabMenu } from "../ui/KebabMenu";
import { useToast } from "../ui/Toast";
import { ConnectionFormDialog } from "./ConnectionFormDialog";
import { ExportDialog } from "./ExportDialog";
import { ImportDialog } from "./ImportDialog";

const CONNECTOR_LABELS: Record<string, string> = {
  obsidian: "Obsidian",
  foundry: "Foundry VTT",
  longstoryshort: "LongStoryShort",
};

export function ConnectionCard({
  connection,
  projectId,
}: {
  connection: Connection;
  projectId: string;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const testConn = useTestConnection(projectId);
  const toggleGrounding = useUpdateConnection(projectId);
  const toggleAutoPush = useUpdateConnection(projectId);
  const deleteConn = useDeleteConnection(projectId);

  const [editOpen, setEditOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const typeLabel =
    CONNECTOR_LABELS[connection.connector_type] ?? connection.connector_type;

  function handleTest() {
    testConn.mutate(connection.id, {
      onSuccess: (result) => {
        if (result.ok) {
          const detail = Object.values(result.info).join(", ");
          toast(`${typeLabel}: ${detail || t("integrations.testOk")}`);
        } else {
          toast(`${typeLabel}: ${t(`integrations.probe.${result.detail_code}`, { defaultValue: result.detail_code })}`);
        }
      },
      onError: (err) => toast(translateApiError(err, t)),
    });
  }

  function handleToggle(field: "use_for_grounding" | "auto_push_after_commit") {
    toggleGrounding.mutate({
      id: connection.id,
      data: {
        name: connection.name,
        config: connection.config,
        use_for_grounding: field === "use_for_grounding" ? !connection.use_for_grounding : connection.use_for_grounding,
        auto_push_after_commit: field === "auto_push_after_commit" ? !connection.auto_push_after_commit : connection.auto_push_after_commit,
      },
    });
  }

  function handleDelete() {
    deleteConn.mutate(connection.id, {
      onSuccess: () => {
        toast(t("integrations.deleted"));
        setDeleteOpen(false);
      },
      onError: (err) => toast(translateApiError(err, t)),
    });
  }

  return (
    <li className="connection-card">
      <div className="connection-card-header">
        <span className="connection-card-type">{typeLabel}</span>
        <span className="connection-card-name">{connection.name}</span>
        <KebabMenu
          items={[
            { label: t("common.edit"), onClick: () => setEditOpen(true) },
            { label: t("common.delete"), onClick: () => setDeleteOpen(true), danger: true },
          ]}
        />
      </div>

      <div className="connection-card-toggles">
        <Checkbox
          label={t("integrations.grounding")}
          checked={connection.use_for_grounding}
          onChange={() => handleToggle("use_for_grounding")}
        />
        <Checkbox
          label={t("integrations.autoPush")}
          checked={connection.auto_push_after_commit}
          onChange={() => handleToggle("auto_push_after_commit")}
        />
      </div>

      <div className="connection-card-actions">
        <button
          type="button"
          className="icon-button"
          onClick={handleTest}
          disabled={testConn.isPending}
          title={t("integrations.test")}
        >
          <Icon name="target" size={14} />
        </button>
        <button
          type="button"
          className="icon-button icon-button-accent"
          onClick={() => setExportOpen(true)}
          title={t("integrations.export")}
        >
          <Icon name="upload" size={14} />
        </button>
        <button
          type="button"
          className="icon-button icon-button-accent"
          onClick={() => setImportOpen(true)}
          title={t("integrations.import")}
        >
          <Icon name="download" size={14} />
        </button>
      </div>

      {editOpen && (
        <ConnectionFormDialog
          projectId={projectId}
          connection={connection}
          onClose={() => setEditOpen(false)}
        />
      )}
      {exportOpen && (
        <ExportDialog
          projectId={projectId}
          connection={connection}
          onClose={() => setExportOpen(false)}
        />
      )}
      {importOpen && (
        <ImportDialog
          projectId={projectId}
          connection={connection}
          onClose={() => setImportOpen(false)}
        />
      )}
      {deleteOpen && (
        <ConfirmDialog
          title={t("integrations.deleteTitle")}
          body={t("integrations.deleteBody", { name: connection.name })}
          confirmLabel={t("common.delete")}
          onConfirm={handleDelete}
          onCancel={() => setDeleteOpen(false)}
        />
      )}
    </li>
  );
}
