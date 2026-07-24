// In-memory fake backend state for the GitHub Pages demo. Everything lives in
// module-level arrays that are seeded once at import time; a full page reload
// re-imports the module and resets the campaign, which is the intended "the
// next visitor sees a pristine world" behaviour (see the demo plan). Nothing
// here is reachable in the real build — client.ts only imports this module when
// import.meta.env.VITE_DEMO is set, and the dynamic import is tree-shaken out
// otherwise.
import type { AgentChatMessage, AgentSessionDetail } from "../agent";
import type { Edge, Entity, Project } from "../types";
import { buildSeed } from "./seed";

export interface DemoDb {
  projects: Project[];
  entities: Entity[];
  edges: Edge[];
  /** Full detail objects (messages included); the list endpoint strips them. */
  sessions: AgentSessionDetail[];
}

const seed = buildSeed();

export const db: DemoDb = {
  projects: seed.projects,
  entities: seed.entities,
  edges: seed.edges,
  sessions: [],
};

let counter = 0;

/** Monotonic id with a readable prefix — good enough for a single-tab demo. */
export function uid(prefix: string): string {
  counter += 1;
  return `${prefix}_${Date.now().toString(36)}${counter}`;
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function findProject(id: string): Project | undefined {
  return db.projects.find((p) => p.id === id);
}

export function findEntity(id: string): Entity | undefined {
  return db.entities.find((e) => e.id === id);
}

export function projectEntities(projectId: string): Entity[] {
  return db.entities.filter((e) => e.project_id === projectId);
}

export function projectEdges(projectId: string): Edge[] {
  return db.edges.filter((e) => e.project_id === projectId);
}

/** Project row as the list endpoint returns it — with live world-size counts
 * the single-entity read leaves at 0 (mirrors the real backend, see
 * api/types.ts Project). */
export function projectWithCounts(project: Project): Project {
  return {
    ...project,
    entity_count: projectEntities(project.id).length,
    edge_count: projectEdges(project.id).length,
  };
}

/** BFS from a root entity out to `depth` hops, following edges in either
 * direction, optionally filtered to a set of edge types. Mirrors the contract
 * of the real /graph/subgraph endpoint (api/graph.ts). */
export function subgraph(
  projectId: string,
  rootId: string,
  depth: number,
  edgeTypes: string[] | undefined,
): { nodes: Entity[]; edges: Edge[] } {
  const allEdges = projectEdges(projectId).filter(
    (e) => !edgeTypes || edgeTypes.length === 0 || edgeTypes.includes(e.type),
  );
  const reached = new Set<string>([rootId]);
  for (let hop = 0; hop < depth; hop += 1) {
    let added = false;
    for (const edge of allEdges) {
      if (reached.has(edge.source_entity_id) && !reached.has(edge.target_entity_id)) {
        reached.add(edge.target_entity_id);
        added = true;
      }
      if (reached.has(edge.target_entity_id) && !reached.has(edge.source_entity_id)) {
        reached.add(edge.source_entity_id);
        added = true;
      }
    }
    if (!added) break;
  }
  const nodes = db.entities.filter((e) => reached.has(e.id));
  const edges = allEdges.filter(
    (e) => reached.has(e.source_entity_id) && reached.has(e.target_entity_id),
  );
  return { nodes, edges };
}

export function newSession(projectId: string): AgentSessionDetail {
  const ts = nowIso();
  const session: AgentSessionDetail = {
    thread_id: uid("thread"),
    project_id: projectId,
    status: "idle",
    title: "",
    input_tokens: 0,
    output_tokens: 0,
    committed_entity_ids: [],
    review: null,
    created_at: ts,
    updated_at: ts,
    messages: [],
  };
  db.sessions.unshift(session);
  return session;
}

export function findSession(threadId: string): AgentSessionDetail | undefined {
  return db.sessions.find((s) => s.thread_id === threadId);
}

export function pushMessage(session: AgentSessionDetail, message: AgentChatMessage): void {
  session.messages.push(message);
  session.updated_at = nowIso();
}
