import { apiClient } from "./client";
import type { Subgraph } from "./types";

export interface SubgraphQuery {
  projectId: string;
  rootId: string;
  depth: number;
  edgeTypes?: string[];
}

export const graphApi = {
  subgraph: ({ projectId, rootId, depth, edgeTypes }: SubgraphQuery) =>
    apiClient.get<Subgraph>(`/api/projects/${projectId}/graph/subgraph`, {
      root_id: rootId,
      depth,
      edge_type: edgeTypes,
    }),
};
