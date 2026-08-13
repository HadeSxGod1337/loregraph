import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useBlocker, useSearchParams } from "react-router-dom";

import { SECRET_MASK_PREFIX, type SettingField } from "../api/appSettings";
import { UpdatesSection } from "../components/layout/UpdatesSection";
import { AppearanceSection } from "../components/settings/AppearanceSection";
import { ReindexPanel } from "../components/settings/ReindexPanel";
import { SettingRow } from "../components/settings/SettingRow";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import {
  useAppSettings,
  useProbeSettings,
  useProviderModels,
  useResetAppSetting,
  useSettingsCatalog,
  useUpdateAppSettings,
} from "../hooks/useAppSettings";
import { translateApiError } from "../i18n/eventText";

/** App-level AI configuration: which provider and models answer, and which
 * embedder indexes. Not project-level — a campaign that was written with a
 * different model is not a different campaign, and the vector store is one
 * per installation.
 *
 * The form renders itself from the backend's provider catalog, so adding a
 * provider is a catalog entry, not a change here. */
type Section =
  | "models"
  | "embeddings"
  | "appearance"
  | "updates"
  | "tracing"
  | "launch";

// Tabs, not a second sidebar: this page is already reached from the rail, and
// a rail inside a rail makes you parse two levels of navigation to change one
// model name.
const TABS: { id: Section; labelKey: string }[] = [
  { id: "models", labelKey: "appSettings.navModels" },
  { id: "embeddings", labelKey: "appSettings.navEmbeddings" },
  { id: "appearance", labelKey: "appSettings.navAppearance" },
  { id: "updates", labelKey: "appSettings.navUpdates" },
  { id: "tracing", labelKey: "appSettings.navTracing" },
  { id: "launch", labelKey: "appSettings.navLaunch" },
];

const AGENT_FIELDS = [
  "agent_run_token_budget",
  "web_search_enabled",
  "agent_prompt_caching",
] as const;

const TRACING_FIELDS = [
  "tracing_provider",
  "langsmith_api_key",
  "langsmith_project",
  "langsmith_endpoint",
  "langfuse_public_key",
  "langfuse_secret_key",
  "langfuse_host",
] as const;

function isSection(value: string | null): value is Section {
  return value !== null && TABS.some((item) => item.id === value);
}

/** Sections that are pure preferences: they save themselves as you click, so
 * the page's save bar would have nothing to do. */
const SELF_SAVING: Section[] = ["appearance", "updates", "launch"];

export function AppSettingsPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [section, setSection] = useState<Section>(
    isSection(searchParams.get("section")) ? (searchParams.get("section") as Section) : "models",
  );

  const { data: settings, isLoading, error } = useAppSettings();
  const { data: catalog } = useSettingsCatalog();
  const update = useUpdateAppSettings();
  const reset = useResetAppSetting();
  const probe = useProbeSettings();

  /** Edits not yet saved, keyed by field name. Empty means the form matches
   * what the server holds. */
  const [draft, setDraft] = useState<Record<string, unknown>>({});

  const provider = useMemo(() => {
    const providerId = (draft.llm_provider ?? settings?.fields.llm_provider?.value) as
      | string
      | undefined;
    return catalog?.providers.find((item) => item.id === providerId);
  }, [catalog, draft.llm_provider, settings]);

  const embeddingProvider = useMemo(() => {
    const providerId = (draft.embedding_provider ??
      settings?.fields.embedding_provider?.value) as string | undefined;
    return catalog?.embedding_providers.find((item) => item.id === providerId);
  }, [catalog, draft.embedding_provider, settings]);

  // Live model list only for providers that publish one, and only once a key
  // is stored — otherwise the request is guaranteed to come back empty.
  const { data: providerModels } = useProviderModels(
    Boolean(provider?.supports_model_listing) && Boolean(settings?.llm_configured),
  );

  const isDirty = Object.keys(draft).length > 0;

  // Leaving with an unsaved key half-typed loses it silently otherwise —
  // same guard the project settings page uses.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty && currentLocation.pathname !== nextLocation.pathname,
  );

  useEffect(() => {
    if (!isDirty) return;
    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  function selectSection(next: Section) {
    setSection(next);
    setSearchParams(next === "models" ? {} : { section: next }, { replace: true });
  }

  function fieldValue(name: string): unknown {
    // Unsaved edit first, then whatever the server holds. For a secret that
    // is the mask, never the key — sending the mask back unchanged is what
    // means "keep it".
    if (name in draft) return draft[name];
    return settings?.fields[name]?.value;
  }

  function setField(name: string, value: unknown) {
    setDraft((current) => ({ ...current, [name]: value }));
  }

  function handleSave() {
    update.mutate(draft, {
      onSuccess: (result) => {
        setDraft({});
        toast(
          result.reindex_started
            ? t("appSettings.savedReindexing")
            : result.restart_required_fields.length > 0
              ? t("appSettings.savedRestartNeeded")
              : t("appSettings.saved"),
        );
      },
    });
  }

  function handleReset(name: string) {
    reset.mutate(name, {
      onSuccess: () => {
        setDraft((current) => {
          const next = { ...current };
          delete next[name];
          return next;
        });
        toast(t("appSettings.resetDone"));
      },
    });
  }

  function handleUseProviderDefaults() {
    if (provider === undefined) return;
    const defaults: Record<string, unknown> = {};
    for (const tier of catalog?.model_tiers ?? []) {
      const model = provider.default_models[tier];
      if (model !== undefined) defaults[`llm_model_${tier}`] = model;
    }
    setDraft((current) => ({ ...current, ...defaults }));
  }

  function handleProbe(target: "llm" | "embeddings") {
    probe.mutate({ section: target, values: draft });
  }

  if (isLoading || settings === undefined || catalog === undefined) {
    return <p>{error ? translateApiError(error, t) : t("common.loading")}</p>;
  }

  const field = (name: string): SettingField | undefined => settings.fields[name];

  return (
    <div className="project-settings-page">
      <div className="settings-page-head">
        <h1>{t("appSettings.heading")}</h1>
        <p className="field-hint">{t("appSettings.subheading")}</p>
      </div>

      <div className="settings-tabbed">
        <nav className="settings-tabs" aria-label={t("appSettings.heading")}>
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={"settings-tab" + (section === item.id ? " active" : "")}
              aria-current={section === item.id ? "page" : undefined}
              onClick={() => selectSection(item.id)}
            >
              {t(item.labelKey)}
            </button>
          ))}
        </nav>

        <div className="settings-panel">
          {section === "models" && (
            <section className="settings-card">
              <div className="settings-card-head">
                <h2>{t("appSettings.providerHeading")}</h2>
                <p className="field-hint">{t("appSettings.providerHint")}</p>
              </div>

              <SettingRow
                field={field("llm_provider")}
                label={t("appSettings.providerLabel")}
                value={fieldValue("llm_provider")}
                options={catalog.providers.map((item) => ({
                  value: item.id,
                  label: item.label,
                }))}
                onChange={(value) => setField("llm_provider", value)}
                onReset={handleReset}
              />

              {provider?.api_key_field != null && (
                <SettingRow
                  field={field(provider.api_key_field)}
                  label={t("appSettings.apiKeyLabel")}
                  hint={
                    provider.key_prefix_hint
                      ? t("appSettings.apiKeyHint", { prefix: provider.key_prefix_hint })
                      : undefined
                  }
                  value={fieldValue(provider.api_key_field)}
                  placeholder={SECRET_MASK_PREFIX}
                  linkUrl={provider.console_url}
                  linkLabel={t("appSettings.getKeyLink")}
                  onChange={(value) => setField(provider.api_key_field!, value)}
                  onReset={handleReset}
                />
              )}

              {provider?.base_url_field != null && (
                <SettingRow
                  field={field(provider.base_url_field)}
                  label={t("appSettings.baseUrlLabel")}
                  value={fieldValue(provider.base_url_field)}
                  onChange={(value) => setField(provider.base_url_field!, value)}
                  onReset={handleReset}
                />
              )}

              <div className="settings-editable-divider" />

              <div className="settings-card-head">
                <h2>{t("appSettings.modelsHeading")}</h2>
                <p className="field-hint">{t("appSettings.modelsHint")}</p>
              </div>

              {catalog.model_tiers.map((tier) => (
                <SettingRow
                  key={tier}
                  field={field(`llm_model_${tier}`)}
                  label={t(`appSettings.tier.${tier}`)}
                  hint={t(`appSettings.tierHint.${tier}`)}
                  value={fieldValue(`llm_model_${tier}`)}
                  suggestions={
                    providerModels?.models.length
                      ? providerModels.models
                      : (provider?.suggested_models ?? [])
                  }
                  onChange={(value) => setField(`llm_model_${tier}`, value)}
                  onReset={handleReset}
                />
              ))}

              <div className="settings-save-row">
                <button type="button" onClick={handleUseProviderDefaults}>
                  {t("appSettings.useDefaults")}
                </button>
                <button
                  type="button"
                  disabled={probe.isPending}
                  onClick={() => handleProbe("llm")}
                >
                  {probe.isPending && <span className="spinner" aria-hidden="true" />}
                  {t("appSettings.testButton")}
                </button>
                {probe.data !== undefined && !probe.isPending && (
                  <span className={probe.data.ok ? "probe-ok" : "error-text"}>
                    {probe.data.ok
                      ? t("appSettings.testOk", { ms: probe.data.latency_ms })
                      : t("appSettings.testFailed", { error: probe.data.error })}
                  </span>
                )}
              </div>

              <div className="settings-editable-divider" />

              <div className="settings-card-head">
                <h2>{t("appSettings.agentHeading")}</h2>
                <p className="field-hint">{t("appSettings.agentHint")}</p>
              </div>

              {AGENT_FIELDS.map((name) => (
                <SettingRow
                  key={name}
                  field={field(name)}
                  label={t(`appSettings.field.${name}`)}
                  hint={t(`appSettings.fieldHint.${name}`)}
                  value={fieldValue(name)}
                  onChange={(value) => setField(name, value)}
                  onReset={handleReset}
                />
              ))}
            </section>
          )}

          {section === "embeddings" && (
            <section className="settings-card">
              <div className="settings-card-head">
                <h2>{t("appSettings.embeddingsHeading")}</h2>
                <p className="field-hint">{t("appSettings.embeddingsHint")}</p>
              </div>

              <SettingRow
                field={field("embedding_provider")}
                label={t("appSettings.embeddingProviderLabel")}
                value={fieldValue("embedding_provider")}
                options={catalog.embedding_providers.map((item) => ({
                  value: item.id,
                  label: item.label,
                }))}
                onChange={(value) => setField("embedding_provider", value)}
                onReset={handleReset}
              />

              {embeddingProvider?.local && (
                <p className="field-hint">{t("appSettings.embeddingLocalNote")}</p>
              )}

              {embeddingProvider?.model_field != null && (
                <SettingRow
                  field={field(embeddingProvider.model_field)}
                  label={t("appSettings.embeddingModelLabel")}
                  value={fieldValue(embeddingProvider.model_field)}
                  suggestions={embeddingProvider.suggested_models}
                  onChange={(value) => setField(embeddingProvider.model_field!, value)}
                  onReset={handleReset}
                />
              )}

              {embeddingProvider?.api_key_field != null && (
                <SettingRow
                  field={field(embeddingProvider.api_key_field)}
                  label={t("appSettings.apiKeyLabel")}
                  value={fieldValue(embeddingProvider.api_key_field)}
                  placeholder={SECRET_MASK_PREFIX}
                  onChange={(value) => setField(embeddingProvider.api_key_field!, value)}
                  onReset={handleReset}
                />
              )}

              <p className="field-hint warning-hint">
                {t("appSettings.embeddingSwitchWarning")}
              </p>

              <div className="settings-save-row">
                <button
                  type="button"
                  disabled={probe.isPending}
                  onClick={() => handleProbe("embeddings")}
                >
                  {probe.isPending && <span className="spinner" aria-hidden="true" />}
                  {t("appSettings.testButton")}
                </button>
                {probe.data !== undefined && !probe.isPending && (
                  <span className={probe.data.ok ? "probe-ok" : "error-text"}>
                    {probe.data.ok
                      ? t("appSettings.testOkDimensions", {
                          ms: probe.data.latency_ms,
                          dimensions: probe.data.dimensions ?? "?",
                        })
                      : t("appSettings.testFailed", { error: probe.data.error })}
                  </span>
                )}
              </div>

              <div className="settings-editable-divider" />

              <ReindexPanel settings={settings} />
            </section>
          )}

          {section === "appearance" && <AppearanceSection />}

          {section === "updates" && (
            <section className="settings-card">
              <div className="settings-card-head">
                <h2>{t("appSettings.updatesHeading")}</h2>
                <p className="field-hint">{t("appSettings.updatesHint")}</p>
              </div>
              <UpdatesSection />
            </section>
          )}

          {section === "tracing" && (
            <section className="settings-card">
              <div className="settings-card-head">
                <h2>{t("appSettings.tracingHeading")}</h2>
                <p className="field-hint">{t("appSettings.tracingHint")}</p>
              </div>

              {TRACING_FIELDS.map((name) => (
                <SettingRow
                  key={name}
                  field={field(name)}
                  label={t(`appSettings.field.${name}`)}
                  value={fieldValue(name)}
                  options={
                    name === "tracing_provider"
                      ? [
                          { value: "disabled", label: t("appSettings.tracingDisabled") },
                          { value: "langsmith", label: "LangSmith" },
                          { value: "langfuse", label: "Langfuse" },
                        ]
                      : undefined
                  }
                  onChange={(value) => setField(name, value)}
                  onReset={handleReset}
                />
              ))}
            </section>
          )}

          {section === "launch" && (
            <section className="settings-card readonly">
              <div className="settings-card-head">
                <h2>{t("appSettings.launchHeading")}</h2>
                <p className="field-hint">{t("appSettings.launchHint")}</p>
              </div>
              <dl className="launch-only-list">
                <dt>{t("appSettings.launch.dataDir")}</dt>
                <dd>{settings.launch_only.data_dir}</dd>
                <dt>{t("appSettings.launch.port")}</dt>
                <dd>{settings.launch_only.frontend_port}</dd>
                <dt>{t("appSettings.launch.playMode")}</dt>
                <dd>{t(settings.launch_only.play_mode_enabled ? "common.on" : "common.off")}</dd>
                <dt>{t("appSettings.launch.internetMode")}</dt>
                <dd>
                  {t(settings.launch_only.internet_mode_enabled ? "common.on" : "common.off")}
                </dd>
                <dt>{t("appSettings.launch.tls")}</dt>
                <dd>{t(settings.launch_only.tls_enabled ? "common.on" : "common.off")}</dd>
                <dt>{t("appSettings.launch.logLevel")}</dt>
                <dd>{settings.launch_only.log_level}</dd>
              </dl>
            </section>
          )}

          {!SELF_SAVING.includes(section) && (
            <div className="settings-editable-foot">
              <span className={"dirty-hint" + (isDirty ? "" : " settings-saved-hint")}>
                {isDirty ? t("appSettings.unsavedChanges") : t("appSettings.allSaved")}
              </span>
              <div className="settings-save-row">
                {update.isError && (
                  <span className="error-text">{translateApiError(update.error, t)}</span>
                )}
                <button
                  type="button"
                  className="button-primary"
                  disabled={!isDirty || update.isPending}
                  onClick={handleSave}
                >
                  {update.isPending && <span className="spinner" aria-hidden="true" />}
                  {update.isPending ? t("appSettings.saving") : t("appSettings.saveButton")}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {blocker.state === "blocked" && (
        <ConfirmDialog
          title={t("common.leaveTitle")}
          body={t("common.leaveBody")}
          confirmLabel={t("common.leaveButton")}
          onConfirm={() => blocker.proceed()}
          onCancel={() => blocker.reset()}
        />
      )}
    </div>
  );
}
