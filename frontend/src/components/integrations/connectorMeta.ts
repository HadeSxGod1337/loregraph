import type { Connection, ConnectorType } from "../../api/types";

/** Display names for the connector types we ship. An unregistered type still
 * renders — under its raw name — so a backend that grew a connector before
 * the frontend did degrades to "usable", not "blank". */
const CONNECTOR_LABELS: Record<string, string> = {
  obsidian: "Obsidian",
  foundry: "Foundry VTT",
  longstoryshort: "LongStoryShort",
  mcp: "MCP server",
};

export const LSS_CONNECTOR_TYPE = "longstoryshort";

export function connectorLabel(connectorType: string): string {
  return CONNECTOR_LABELS[connectorType] ?? connectorType;
}

/** What a connection can actually do, straight from GET /api/connectors.
 *
 * The UI used to offer every action on every connection: an Export button on
 * a LongStoryShort connection (which has no exporter and answers 422), an
 * "auto-push after commit" switch on a connection that can never push. Both
 * capability checks live here so no surface can drift back into promising
 * something the backend refuses. */
export interface Capabilities {
  canImport: boolean;
  canExport: boolean;
  /** The connection can answer the agent's questions while it works —
   * the only thing "use for grounding" can switch on. */
  canFeedAgent: boolean;
  canMigrate: boolean;
}

export function capabilitiesOf(
  connectorType: string,
  connectorTypes: ConnectorType[],
): Capabilities {
  const declared =
    connectorTypes.find((type) => type.connector_type === connectorType)
      ?.capabilities ?? [];
  return {
    canImport: declared.includes("import"),
    canExport: declared.includes("export"),
    canFeedAgent: declared.includes("live"),
    canMigrate: declared.includes("ingest"),
  };
}

export function connectionCapabilities(
  connection: Connection,
  connectorTypes: ConnectorType[],
): Capabilities {
  return capabilitiesOf(connection.connector_type, connectorTypes);
}
