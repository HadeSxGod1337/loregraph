import { apiClient } from "./client";

/** Sentinel the backend sends instead of a stored API key, and accepts back
 * unchanged to mean "keep it" (see schemas/app_settings.py). */
export const SECRET_MASK_PREFIX = "••••";

export type SettingSource = "db" | "env" | "default";

export interface SettingField {
  name: string;
  /** Masked for secrets; null when nothing is stored. */
  value: unknown;
  source: SettingSource;
  secret: boolean;
  is_set: boolean;
  restart_required: boolean;
}

export interface ProviderInfo {
  id: string;
  label: string;
  api_key_field: string | null;
  base_url_field: string | null;
  console_url: string | null;
  key_prefix_hint: string | null;
  default_models: Record<string, string>;
  suggested_models: string[];
  supports_model_listing: boolean;
}

export interface EmbeddingProviderInfo {
  id: string;
  label: string;
  model_field: string | null;
  api_key_field: string | null;
  base_url_field: string | null;
  local: boolean;
  suggested_models: string[];
}

export interface SettingsCatalog {
  providers: ProviderInfo[];
  embedding_providers: EmbeddingProviderInfo[];
  model_tiers: string[];
  editable_fields: string[];
}

export interface ReindexStatus {
  state: "idle" | "running" | "done" | "error";
  total_projects: number;
  done_projects: number;
  current_project: string | null;
  current_source: string | null;
  total_sources: number;
  entities_indexed: number;
  sources_indexed: number;
  error: string | null;
  model_id: string | null;
}

export interface LaunchOnlySettings {
  data_dir: string;
  frontend_port: number;
  play_mode_enabled: boolean;
  internet_mode_enabled: boolean;
  tls_enabled: boolean;
  trust_loopback: boolean;
  log_level: string;
}

export interface AppSettings {
  fields: Record<string, SettingField>;
  llm_configured: boolean;
  embeddings_enabled: boolean;
  embedding_model_id: string | null;
  reindex: ReindexStatus;
  launch_only: LaunchOnlySettings;
}

export interface AppSettingsUpdateResult {
  settings: AppSettings;
  restart_required_fields: string[];
  reindex_required: boolean;
  reindex_started: boolean;
}

export interface SettingsProbeResult {
  ok: boolean;
  latency_ms: number;
  error: string | null;
  dimensions: number | null;
}

export interface ProviderModels {
  models: string[];
  error: string | null;
}

export const appSettingsApi = {
  get: () => apiClient.get<AppSettings>("/api/settings"),
  catalog: () => apiClient.get<SettingsCatalog>("/api/settings/catalog"),
  models: () => apiClient.get<ProviderModels>("/api/settings/models"),
  update: (values: Record<string, unknown>) =>
    apiClient.put<AppSettingsUpdateResult>("/api/settings", { values }),
  reset: (field: string) =>
    apiClient.delete<AppSettingsUpdateResult>(`/api/settings/${field}`),
  probe: (section: "llm" | "embeddings", values: Record<string, unknown>) =>
    apiClient.post<SettingsProbeResult>("/api/settings/probe", { section, values }),
  startReindex: () => apiClient.post<ReindexStatus>("/api/settings/reindex"),
  reindexStatus: () => apiClient.get<ReindexStatus>("/api/settings/reindex"),
};
