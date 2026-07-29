import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { templatesApi } from "../api/templates";
import type { EntityTemplateCreate, EntityTemplateUpdate } from "../api/types";

export function useTemplates(projectId: string) {
  return useQuery({
    queryKey: ["templates", projectId],
    queryFn: () => templatesApi.list(projectId),
    // Templates change only when a DM edits one in the designer, which
    // invalidates this key explicitly. Everything that renders a sheet reads
    // this list (every drawer, every editor, the picker), so without a stale
    // time each of those mounts refetched four built-in templates plus the
    // project's own — a payload dominated by the Character sheet's layout.
    staleTime: 5 * 60 * 1000,
  });
}

/** The template an entity is explicitly bound to, or undefined (plain view)
 * when unbound, still loading, or the bound template no longer exists. */
export function useTemplateById(
  projectId: string,
  templateId: string | null | undefined,
) {
  const { data } = useTemplates(projectId);
  if (!templateId) return undefined;
  return (data ?? []).find((t) => t.id === templateId);
}

export function useCreateTemplate(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EntityTemplateCreate) =>
      templatesApi.create(projectId, data),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["templates", projectId] }),
  });
}

export function useUpdateTemplate(projectId: string, id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EntityTemplateUpdate) =>
      templatesApi.update(projectId, id, data),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["templates", projectId] }),
  });
}

export function useDeleteTemplate(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => templatesApi.remove(projectId, id),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["templates", projectId] }),
  });
}

// Instantiation creates an entity, so it invalidates the entity/graph caches
// (same set as useCreateEntity), not the templates list.
export function useInstantiateTemplate(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, title }: { templateId: string; title: string }) =>
      templatesApi.instantiate(projectId, templateId, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["entities", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["subgraph", projectId] });
    },
  });
}
