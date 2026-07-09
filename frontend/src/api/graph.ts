import { apiClient } from "./client";
import type { Subgraph } from "./types";

export interface SubgraphQuery {
  rootId: string;
  depth: number;
  edgeTypes?: string[];
}

export const graphApi = {
  subgraph: ({ rootId, depth, edgeTypes }: SubgraphQuery) =>
    apiClient.get<Subgraph>("/api/graph/subgraph", {
      root_id: rootId,
      depth,
      edge_type: edgeTypes,
    }),
};
