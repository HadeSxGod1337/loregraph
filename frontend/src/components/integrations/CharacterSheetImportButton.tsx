import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Connection } from "../../api/types";
import {
  useConnections,
  useConnectorTypes,
  useCreateConnection,
} from "../../hooks/useConnections";
import { translateApiError } from "../../i18n/eventText";
import { Icon } from "../ui/Icon";
import { useToast } from "../ui/Toast";
import { LSS_CONNECTOR_TYPE } from "./connectorMeta";
import { ImportDialog } from "./ImportDialog";

/** "Import character sheets", where a DM looks for it: on the party's own
 * page, not three levels into project settings.
 *
 * Importing needed a LongStoryShort connection to exist first — a setup step
 * with an empty config form, whose only real job is to own the provenance
 * links that let a re-import refresh a character instead of cloning them.
 * Nothing about that is the DM's decision, so the button makes the
 * connection itself the first time it is used. */
export function CharacterSheetImportButton({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const toast = useToast();
  const { data: connections } = useConnections(projectId);
  const { data: connectorTypes } = useConnectorTypes();
  const createConnection = useCreateConnection(projectId);
  const [connection, setConnection] = useState<Connection | null>(null);

  const existing = connections?.find(
    (candidate) => candidate.connector_type === LSS_CONNECTOR_TYPE,
  );
  // Nothing to offer if this build's backend doesn't register the connector.
  const supported = connectorTypes?.some(
    (type) => type.connector_type === LSS_CONNECTOR_TYPE,
  );
  if (!supported) return null;

  function handleClick() {
    if (existing) {
      setConnection(existing);
      return;
    }
    createConnection.mutate(
      {
        connector_type: LSS_CONNECTOR_TYPE,
        name: "LongStoryShort",
        config: {},
        use_for_grounding: false,
        auto_push_after_commit: false,
      },
      {
        onSuccess: (created) => setConnection(created),
        onError: (err) => toast(translateApiError(err, t)),
      },
    );
  }

  return (
    <>
      <button
        type="button"
        className="button-ghost"
        onClick={handleClick}
        disabled={createConnection.isPending}
      >
        <Icon name="download" />
        {t("entities.importSheets")}
      </button>
      {connection && (
        <ImportDialog
          projectId={projectId}
          connection={connection}
          onClose={() => setConnection(null)}
        />
      )}
    </>
  );
}
