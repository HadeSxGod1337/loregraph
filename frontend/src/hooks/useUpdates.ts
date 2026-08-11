import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { updatesApi } from "../api/updates";
import type { UpdatePreferences } from "../api/types";

/** Global, not project-scoped — the launcher checks the git remote for the
 * whole app. Only the launcher touches the remote (see the backend's
 * update_status service), so this just polls the file it wrote; a 5-minute
 * refetch keeps the badge roughly in sync without hammering anything. */
export function useUpdateStatus() {
  return useQuery({
    queryKey: ["update-status"],
    queryFn: () => updatesApi.get(),
    staleTime: 60_000,
    refetchInterval: 300_000,
  });
}

export function useSetUpdatePreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (prefs: UpdatePreferences) => updatesApi.setPreferences(prefs),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["update-status"] });
    },
  });
}
