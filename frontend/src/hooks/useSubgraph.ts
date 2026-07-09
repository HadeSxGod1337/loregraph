import { useQuery } from "@tanstack/react-query";

import { graphApi } from "../api/graph";

export function useSubgraph(
  rootId: string | undefined,
  depth: number,
  edgeTypes: string[] | undefined,
) {
  return useQuery({
    queryKey: ["subgraph", rootId, depth, edgeTypes],
    queryFn: () => graphApi.subgraph({ rootId: rootId!, depth, edgeTypes }),
    enabled: rootId !== undefined && rootId !== "",
  });
}
