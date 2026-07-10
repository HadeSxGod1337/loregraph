import { useQuery } from "@tanstack/react-query";

import { graphApi } from "../api/graph";

export function useSubgraph(
  projectId: string,
  rootId: string | undefined,
  depth: number,
  edgeTypes: string[] | undefined,
) {
  return useQuery({
    queryKey: ["subgraph", projectId, rootId, depth, edgeTypes],
    queryFn: () => graphApi.subgraph({ projectId, rootId: rootId!, depth, edgeTypes }),
    enabled: rootId !== undefined && rootId !== "",
  });
}
