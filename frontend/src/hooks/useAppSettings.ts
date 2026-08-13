import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { appSettingsApi } from "../api/appSettings";

const SETTINGS_KEY = ["appSettings"];
const REINDEX_KEY = ["appSettings", "reindex"];

/** How often the settings page asks how the rebuild is going. Fast enough to
 * feel live, slow enough that a long reindex isn't answering a request per
 * indexed entity. */
const REINDEX_POLL_MS = 1500;

export function useAppSettings() {
  return useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: () => appSettingsApi.get(),
  });
}

export function useSettingsCatalog() {
  return useQuery({
    queryKey: ["appSettings", "catalog"],
    // Provider metadata is code, not state: it can't change while the page
    // is open, so it is fetched once and kept.
    staleTime: Infinity,
    queryFn: () => appSettingsApi.catalog(),
  });
}

/** Live model list from the provider, for the model field's suggestions.
 * `enabled` is false for providers that publish none. */
export function useProviderModels(enabled: boolean) {
  return useQuery({
    queryKey: ["appSettings", "models"],
    queryFn: () => appSettingsApi.models(),
    enabled,
    staleTime: 60_000,
  });
}

export function useUpdateAppSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, unknown>) => appSettingsApi.update(values),
    onSuccess: (result) => {
      queryClient.setQueryData(SETTINGS_KEY, result.settings);
      // The provider (and so the model list) may have changed under it.
      void queryClient.invalidateQueries({ queryKey: ["appSettings", "models"] });
      // Which model answers is part of the assistant's own config probe.
      void queryClient.invalidateQueries({ queryKey: ["agent-config"] });
    },
  });
}

export function useResetAppSetting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (field: string) => appSettingsApi.reset(field),
    onSuccess: (result) => {
      queryClient.setQueryData(SETTINGS_KEY, result.settings);
      void queryClient.invalidateQueries({ queryKey: ["appSettings", "models"] });
      void queryClient.invalidateQueries({ queryKey: ["agent-config"] });
    },
  });
}

export function useProbeSettings() {
  return useMutation({
    mutationFn: ({
      section,
      values,
    }: {
      section: "llm" | "embeddings";
      values: Record<string, unknown>;
    }) => appSettingsApi.probe(section, values),
  });
}

/** Reindex progress. Polls only while a rebuild is actually running — the
 * job has no push channel, and an idle page must not poll forever. */
export function useReindexStatus(running: boolean) {
  return useQuery({
    queryKey: REINDEX_KEY,
    queryFn: () => appSettingsApi.reindexStatus(),
    refetchInterval: running ? REINDEX_POLL_MS : false,
    enabled: running,
  });
}

export function useStartReindex() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => appSettingsApi.startReindex(),
    onSuccess: (status) => {
      queryClient.setQueryData(REINDEX_KEY, status);
      void queryClient.invalidateQueries({ queryKey: SETTINGS_KEY });
    },
  });
}
