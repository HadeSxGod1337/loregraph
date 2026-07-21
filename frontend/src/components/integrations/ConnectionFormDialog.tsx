import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Connection, ConnectorType } from "../../api/types";
import {
  useCreateConnection,
  useUpdateConnection,
} from "../../hooks/useConnections";
import { translateApiError } from "../../i18n/eventText";
import { Checkbox } from "../ui/Checkbox";
import { useToast } from "../ui/Toast";

/** Hardcoded config field definitions per connector type. No JSON-schema
 * forms — every supported type has a small, stable config shape. "lines"
 * fields are one value per line (→ a string array); "kv" fields are one
 * KEY=VALUE per line (→ a string map) — used only by "mcp", the one type
 * whose config isn't flat strings/numbers (an arbitrary MCP server's own
 * argv/env). */
const CONFIG_FIELDS: Record<
  string,
  {
    key: string;
    label: string;
    type?: "password" | "text" | "lines" | "kv";
    secret?: boolean;
  }[]
> = {
  obsidian: [
    { key: "vault_path", label: "integrations.config.vaultPath" },
    { key: "subfolder", label: "integrations.config.subfolder" },
  ],
  foundry: [
    { key: "node_command", label: "integrations.config.nodeCommand" },
    { key: "mcp_server_path", label: "integrations.config.mcpServerPath" },
    { key: "foundry_host", label: "integrations.config.foundryHost" },
    { key: "foundry_port", label: "integrations.config.foundryPort" },
    { key: "request_timeout_s", label: "integrations.config.timeout" },
  ],
  longstoryshort: [],
  mcp: [
    { key: "command", label: "integrations.config.mcpCommand" },
    { key: "args", label: "integrations.config.mcpArgs", type: "lines" },
    { key: "env", label: "integrations.config.mcpEnv", type: "kv" },
    { key: "request_timeout_s", label: "integrations.config.timeout" },
    {
      key: "allowed_tools",
      label: "integrations.config.mcpAllowedTools",
      type: "lines",
    },
  ],
};

const CONNECTOR_LABELS: Record<string, string> = {
  obsidian: "Obsidian",
  foundry: "Foundry VTT",
  longstoryshort: "LongStoryShort",
  mcp: "MCP server",
};

function linesToArray(raw: string): string[] {
  return raw
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function linesToRecord(raw: string): Record<string, string> {
  const record: Record<string, string> = {};
  for (const line of linesToArray(raw)) {
    const eq = line.indexOf("=");
    if (eq > 0) record[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
  }
  return record;
}

/** Flattens a stored config value back into the textarea/input string the
 * form edits — the inverse of linesToArray/linesToRecord. */
function valueToEditableString(value: unknown): string {
  if (Array.isArray(value)) return value.join("\n");
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${k}=${v}`)
      .join("\n");
  }
  return String(value ?? "");
}

export function ConnectionFormDialog({
  projectId,
  connectorTypes,
  connection,
  onClose,
}: {
  projectId: string;
  connectorTypes: ConnectorType[];
  connection?: Connection;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const create = useCreateConnection(projectId);
  const update = useUpdateConnection(projectId);

  const isEdit = !!connection;
  const [connectorType, setConnectorType] = useState(
    connection?.connector_type ?? connectorTypes[0]?.connector_type ?? "",
  );
  const [name, setName] = useState(connection?.name ?? "");
  const [config, setConfig] = useState<Record<string, string>>(() => {
    if (!connection) return {};
    const flat: Record<string, string> = {};
    for (const [k, v] of Object.entries(connection.config)) {
      flat[k] = valueToEditableString(v);
    }
    return flat;
  });
  const [useForGrounding, setUseForGrounding] = useState(
    connection?.use_for_grounding ?? false,
  );
  const [autoPush, setAutoPush] = useState(
    connection?.auto_push_after_commit ?? false,
  );

  const fields = CONFIG_FIELDS[connectorType] ?? [];
  const busy = create.isPending || update.isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Reconstruct typed config from flat string values.
    const typedConfig: Record<string, unknown> = {};
    for (const f of fields) {
      const raw = config[f.key] ?? "";
      if (f.key === "request_timeout_s" || f.key === "foundry_port") {
        typedConfig[f.key] = Number(raw) || (f.key === "foundry_port" ? 31415 : 15);
      } else if (f.type === "lines") {
        typedConfig[f.key] = linesToArray(raw);
      } else if (f.type === "kv") {
        typedConfig[f.key] = linesToRecord(raw);
      } else {
        typedConfig[f.key] = raw;
      }
    }

    if (isEdit) {
      update.mutate(
        {
          id: connection.id,
          data: {
            name,
            config: typedConfig,
            use_for_grounding: useForGrounding,
            auto_push_after_commit: autoPush,
          },
        },
        {
          onSuccess: () => {
            toast(t("integrations.saved"));
            onClose();
          },
          onError: (err) => toast(translateApiError(err, t)),
        },
      );
    } else {
      create.mutate(
        {
          connector_type: connectorType,
          name,
          config: typedConfig,
          use_for_grounding: useForGrounding,
          auto_push_after_commit: autoPush,
        },
        {
          onSuccess: () => {
            toast(t("integrations.created"));
            onClose();
          },
          onError: (err) => toast(translateApiError(err, t)),
        },
      );
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={isEdit ? t("integrations.editTitle") : t("integrations.addTitle")}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{isEdit ? t("integrations.editTitle") : t("integrations.addTitle")}</h2>

        <form onSubmit={handleSubmit}>
          {!isEdit && (
            <label>
              {t("integrations.typeLabel")}
              <select
                value={connectorType}
                onChange={(e) => setConnectorType(e.target.value)}
              >
                {connectorTypes.map((ct) => (
                  <option key={ct.connector_type} value={ct.connector_type}>
                    {CONNECTOR_LABELS[ct.connector_type] ?? ct.connector_type}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label>
            {t("integrations.nameLabel")}
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("integrations.namePlaceholder")}
            />
          </label>

          {fields.map((f) =>
            f.type === "lines" || f.type === "kv" ? (
              <label key={f.key}>
                {t(f.label)}
                <textarea
                  rows={3}
                  value={config[f.key] ?? ""}
                  onChange={(e) =>
                    setConfig((prev) => ({ ...prev, [f.key]: e.target.value }))
                  }
                  placeholder={
                    f.type === "kv" ? "KEY=value" : t("integrations.config.oneLine")
                  }
                />
              </label>
            ) : (
              <label key={f.key}>
                {t(f.label)}
                <input
                  type={f.secret ? "password" : "text"}
                  value={config[f.key] ?? ""}
                  onChange={(e) =>
                    setConfig((prev) => ({ ...prev, [f.key]: e.target.value }))
                  }
                  placeholder={
                    isEdit && connection.config[f.key] !== undefined
                      ? String(connection.config[f.key]).slice(0, 8) + "••••"
                      : ""
                  }
                />
              </label>
            ),
          )}

          <Checkbox
            label={t("integrations.grounding")}
            checked={useForGrounding}
            onChange={(e) => setUseForGrounding(e.target.checked)}
          />
          <Checkbox
            label={t("integrations.autoPush")}
            checked={autoPush}
            onChange={(e) => setAutoPush(e.target.checked)}
          />

          {(create.isError || update.isError) && (
            <p className="error-text">
              {translateApiError(create.error ?? update.error, t)}
            </p>
          )}

          <div className="dialog-actions">
            <button type="button" className="button-ghost" onClick={onClose}>
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              className="button-primary"
              disabled={!name.trim() || busy}
            >
              {busy ? "…" : isEdit ? t("common.save") : t("common.create")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
