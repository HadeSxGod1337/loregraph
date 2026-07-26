import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { sheetPresetsApi } from "../api/sheetPresets";
import type { SheetPresetCreate } from "../api/types";

export function useSheetPresets(projectId: string) {
  return useQuery({
    queryKey: ["sheet-presets", projectId],
    queryFn: () => sheetPresetsApi.list(projectId),
  });
}

export function useCreateSheetPreset(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SheetPresetCreate) => sheetPresetsApi.create(projectId, data),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["sheet-presets", projectId] }),
  });
}

export function useDeleteSheetPreset(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sheetPresetsApi.remove(projectId, id),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["sheet-presets", projectId] }),
  });
}
