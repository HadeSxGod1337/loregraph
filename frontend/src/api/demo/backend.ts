// The demo's in-memory fake backend: a tiny router that answers the same REST
// contract the FastAPI app does, backed by the module-level store. Only ever
// loaded when import.meta.env.VITE_DEMO is set (client.ts dynamic-imports it),
// so none of this ships in the real build.
import { ApiError } from "../client";
import type {
  AgentConfig,
  AgentEvent,
  AgentResumeRequest,
  AgentReviewPayload,
  AgentSession,
  AgentSessionDetail,
  LoreDraft,
} from "../agent";
import type { PositionEntry } from "../entities";
import type {
  Connection,
  Edge,
  EdgeCreate,
  EdgeUpdate,
  Entity,
  EntityCreate,
  EntityField,
  EntityUpdate,
  Project,
  ProjectCreate,
  ProjectExport,
  ProjectUpdate,
} from "../types";
import {
  db,
  findEntity,
  findProject,
  findSession,
  newSession,
  nowIso,
  projectEdges,
  projectEntities,
  projectWithCounts,
  pushMessage,
  subgraph,
  uid,
} from "./store";

type Query = Record<string, string | number | string[] | undefined> | undefined;
type Params = Record<string, string>;

const delay = (ms = 90): Promise<void> => new Promise((r) => setTimeout(r, ms));

function notFound(method: string, path: string): never {
  throw new ApiError(404, `Not Found (${method} ${path} → demo)`, "not_found");
}

// --- tiny path matcher ----------------------------------------------------

function matchPath(pattern: string, path: string): Params | null {
  const pSegs = pattern.split("/");
  const aSegs = path.split("/");
  if (pSegs.length !== aSegs.length) return null;
  const params: Params = {};
  for (let i = 0; i < pSegs.length; i += 1) {
    const p = pSegs[i];
    if (p.startsWith(":")) params[p.slice(1)] = decodeURIComponent(aSegs[i]);
    else if (p !== aSegs[i]) return null;
  }
  return params;
}

function qStr(query: Query, key: string): string | undefined {
  const v = query?.[key];
  return v === undefined ? undefined : String(Array.isArray(v) ? v[0] : v);
}

function qNum(query: Query, key: string, fallback: number): number {
  const v = qStr(query, key);
  return v === undefined ? fallback : Number(v);
}

function qArr(query: Query, key: string): string[] | undefined {
  const v = query?.[key];
  if (v === undefined) return undefined;
  return Array.isArray(v) ? v.map(String) : [String(v)];
}

// --- entity/session serialisation -----------------------------------------

function draftFieldsToEntityFields(
  fields: { key: string; value: string }[],
): EntityField[] {
  return fields.map((f) => ({
    key: f.key,
    field_type: "text",
    value: f.value,
    show_on_card: false,
  }));
}

function stripSession(session: AgentSessionDetail): AgentSession {
  const { messages: _messages, ...rest } = session;
  void _messages;
  return rest;
}

// --- request routing ------------------------------------------------------

type Handler = (m: Params, body: unknown, query: Query) => unknown;

interface Route {
  method: string;
  pattern: string;
  handler: Handler;
}

// Ordered: more specific patterns first so e.g. /entities/positions beats
// /entities/:id. First match wins.
const routes: Route[] = [
  // --- projects ---
  { method: "GET", pattern: "/api/projects", handler: () => db.projects.map(projectWithCounts) },
  {
    method: "POST",
    pattern: "/api/projects",
    handler: (_m, body) => createProject(body as ProjectCreate),
  },
  { method: "POST", pattern: "/api/projects/import", handler: (_m, body) => importProject(body as ProjectExport) },
  { method: "GET", pattern: "/api/projects/:id", handler: (m) => projectWithCounts(requireProject(m.id)) },
  {
    method: "PUT",
    pattern: "/api/projects/:id",
    handler: (m, body) => updateProject(m.id, body as ProjectUpdate),
  },
  { method: "DELETE", pattern: "/api/projects/:id", handler: (m) => deleteProject(m.id) },
  { method: "GET", pattern: "/api/projects/:id/export", handler: (m) => exportProject(m.id) },
  {
    method: "POST",
    pattern: "/api/projects/:id/reindex",
    handler: (m) => ({ indexed: projectEntities(m.id).length }),
  },
  { method: "GET", pattern: "/api/projects/:id/usage", handler: (m) => usageFor(m.id) },

  // --- entities ---
  {
    method: "GET",
    pattern: "/api/projects/:id/entities",
    handler: (m, _b, q) => {
      const type = qStr(q, "type");
      return projectEntities(m.id).filter((e) => !type || e.type === type);
    },
  },
  {
    method: "POST",
    pattern: "/api/projects/:id/entities",
    handler: (m, body) => createEntity(m.id, body as EntityCreate),
  },
  {
    method: "PUT",
    pattern: "/api/projects/:id/entities/positions",
    handler: (m, body) => updatePositions(m.id, body as PositionEntry[]),
  },
  { method: "GET", pattern: "/api/projects/:id/entities/:eid", handler: (m) => requireEntity(m.eid) },
  {
    method: "PUT",
    pattern: "/api/projects/:id/entities/:eid",
    handler: (m, body) => updateEntity(m.eid, body as EntityUpdate),
  },
  { method: "DELETE", pattern: "/api/projects/:id/entities/:eid", handler: (m) => deleteEntity(m.eid) },
  // Icons need real uploads — the demo has none, so these are no-ops that just
  // echo the (unchanged) entity.
  { method: "PUT", pattern: "/api/projects/:id/entities/:eid/icon", handler: (m) => requireEntity(m.eid) },
  { method: "DELETE", pattern: "/api/projects/:id/entities/:eid/icon", handler: (m) => requireEntity(m.eid) },

  // --- edges ---
  {
    method: "GET",
    pattern: "/api/projects/:id/edges",
    handler: (m, _b, q) => {
      const entityId = qStr(q, "entity_id");
      return projectEdges(m.id).filter(
        (e) =>
          !entityId ||
          e.source_entity_id === entityId ||
          e.target_entity_id === entityId,
      );
    },
  },
  {
    method: "POST",
    pattern: "/api/projects/:id/edges",
    handler: (m, body) => createEdge(m.id, body as EdgeCreate),
  },
  {
    method: "PUT",
    pattern: "/api/projects/:id/edges/:eid",
    handler: (m, body) => updateEdge(m.eid, body as EdgeUpdate),
  },
  { method: "DELETE", pattern: "/api/projects/:id/edges/:eid", handler: (m) => deleteEdge(m.eid) },

  // --- graph ---
  {
    method: "GET",
    pattern: "/api/projects/:id/graph/subgraph",
    handler: (m, _b, q) =>
      subgraph(m.id, qStr(q, "root_id") ?? "", qNum(q, "depth", 1), qArr(q, "edge_type")),
  },

  // --- agent (non-streaming) ---
  {
    method: "GET",
    pattern: "/api/agent/config",
    handler: (): AgentConfig => ({
      llm_configured: true,
      llm_provider: "anthropic (demo)",
      vector_enabled: true,
    }),
  },
  {
    method: "POST",
    pattern: "/api/projects/:id/agent/sessions",
    handler: (m) => stripSession(newSession(m.id)),
  },
  {
    method: "GET",
    pattern: "/api/projects/:id/agent/sessions",
    handler: (m) =>
      db.sessions.filter((s) => s.project_id === m.id).map(stripSession),
  },
  {
    method: "GET",
    pattern: "/api/projects/:id/agent/sessions/:tid",
    handler: (m): AgentSessionDetail => requireSession(m.tid),
  },

  // --- integrations / knowledge / attachments / import (stubs) ---
  { method: "GET", pattern: "/api/connectors", handler: () => [{ connector_type: "markdown", capabilities: ["export", "preview"] }] },
  { method: "GET", pattern: "/api/projects/:id/connections", handler: () => [] },
  { method: "POST", pattern: "/api/projects/:id/connections", handler: (m, body) => stubConnection(m.id, body) },
  { method: "PUT", pattern: "/api/projects/:id/connections/:cid", handler: (m, body) => stubConnection(m.id, body, m.cid) },
  { method: "DELETE", pattern: "/api/projects/:id/connections/:cid", handler: () => undefined },
  { method: "POST", pattern: "/api/projects/:id/connections/:cid/test", handler: () => ({ ok: true, detail_code: "demo_ok", info: {} }) },
  { method: "POST", pattern: "/api/projects/:id/connections/:cid/export/preview", handler: () => ({ items: [] }) },
  { method: "POST", pattern: "/api/projects/:id/connections/:cid/export", handler: () => ({ created: 0, updated: 0, skipped: 0, errors: [] }) },
  { method: "POST", pattern: "/api/projects/:id/connections/:cid/import", handler: () => ({ created: 0, updated: 0, skipped: 0, errors: [] }) },
  { method: "GET", pattern: "/api/projects/:id/knowledge", handler: () => [] },
  { method: "GET", pattern: "/api/projects/:id/import-jobs", handler: () => [] },
  { method: "GET", pattern: "/api/entities/:eid/attachments", handler: () => [] },
];

export async function demoRequest(
  method: string,
  path: string,
  query: Query,
  body: unknown,
): Promise<unknown> {
  await delay();
  // File uploads (multipart) have no meaning without a real backend.
  if (body instanceof FormData) {
    throw new ApiError(400, "File uploads are disabled in the demo.", "demo_no_upload");
  }
  for (const route of routes) {
    if (route.method !== method) continue;
    const m = matchPath(route.pattern, path);
    if (m) return route.handler(m, body, query);
  }
  notFound(method, path);
}

// --- project handlers -----------------------------------------------------

function requireProject(id: string): Project {
  const project = findProject(id);
  if (!project) throw new ApiError(404, `Project ${id} not found`, "not_found");
  return project;
}

function createProject(data: ProjectCreate): Project {
  const ts = nowIso();
  const project: Project = {
    id: uid("proj"),
    name: data.name,
    description: data.description ?? null,
    agent_instructions: data.agent_instructions ?? null,
    entity_count: 0,
    edge_count: 0,
    created_at: ts,
    updated_at: ts,
  };
  db.projects.push(project);
  return project;
}

function updateProject(id: string, data: ProjectUpdate): Project {
  const project = requireProject(id);
  project.name = data.name;
  project.description = data.description ?? null;
  project.agent_instructions = data.agent_instructions ?? null;
  project.updated_at = nowIso();
  return projectWithCounts(project);
}

function deleteProject(id: string): undefined {
  requireProject(id);
  db.projects = db.projects.filter((p) => p.id !== id);
  db.entities = db.entities.filter((e) => e.project_id !== id);
  db.edges = db.edges.filter((e) => e.project_id !== id);
  return undefined;
}

function exportProject(id: string): ProjectExport {
  const project = requireProject(id);
  return {
    format_version: 1,
    name: project.name,
    description: project.description,
    entities: projectEntities(id).map((e) => ({
      id: e.id,
      type: e.type,
      title: e.title,
      fields: e.fields,
      icon_attachment_id: null,
      pos_x: e.pos_x,
      pos_y: e.pos_y,
    })),
    edges: projectEdges(id).map((e) => ({
      source_entity_id: e.source_entity_id,
      target_entity_id: e.target_entity_id,
      type: e.type,
      label: e.label,
    })),
    attachments: [],
  };
}

function importProject(payload: ProjectExport): Project {
  const project = createProject({ name: `${payload.name} (imported)`, description: payload.description });
  const idMap = new Map<string, string>();
  for (const e of payload.entities) {
    const newId = uid("ent");
    idMap.set(e.id, newId);
    db.entities.push({
      id: newId,
      project_id: project.id,
      type: e.type,
      title: e.title,
      fields: e.fields,
      icon: null,
      pos_x: e.pos_x,
      pos_y: e.pos_y,
      created_at: nowIso(),
      updated_at: nowIso(),
    });
  }
  for (const e of payload.edges) {
    const source = idMap.get(e.source_entity_id);
    const target = idMap.get(e.target_entity_id);
    if (!source || !target) continue;
    db.edges.push({
      id: uid("edge"),
      project_id: project.id,
      source_entity_id: source,
      target_entity_id: target,
      type: e.type,
      label: e.label,
      created_at: nowIso(),
    });
  }
  return projectWithCounts(project);
}

function usageFor(id: string) {
  requireProject(id);
  return [
    { node: "compose_lore", model: "claude-sonnet-5", calls: 4, input_tokens: 12800, output_tokens: 3100, cache_read_tokens: 9000, cache_creation_tokens: 2400 },
    { node: "extract_relationships", model: "claude-haiku-4-5", calls: 6, input_tokens: 5400, output_tokens: 900, cache_read_tokens: 0, cache_creation_tokens: 0 },
  ];
}

// --- entity handlers ------------------------------------------------------

function requireEntity(id: string): Entity {
  const entity = findEntity(id);
  if (!entity) throw new ApiError(404, `Entity ${id} not found`, "not_found");
  return entity;
}

function createEntity(projectId: string, data: EntityCreate): Entity {
  const ts = nowIso();
  const entity: Entity = {
    id: uid("ent"),
    project_id: projectId,
    type: data.type,
    title: data.title,
    fields: data.fields,
    icon: null,
    pos_x: null,
    pos_y: null,
    created_at: ts,
    updated_at: ts,
  };
  db.entities.push(entity);
  return entity;
}

function updateEntity(id: string, data: EntityUpdate): Entity {
  const entity = requireEntity(id);
  entity.type = data.type;
  entity.title = data.title;
  entity.fields = data.fields;
  entity.updated_at = nowIso();
  return entity;
}

function deleteEntity(id: string): undefined {
  requireEntity(id);
  db.entities = db.entities.filter((e) => e.id !== id);
  db.edges = db.edges.filter(
    (e) => e.source_entity_id !== id && e.target_entity_id !== id,
  );
  return undefined;
}

function updatePositions(projectId: string, positions: PositionEntry[]): Entity[] {
  for (const pos of positions) {
    const entity = findEntity(pos.entity_id);
    if (entity && entity.project_id === projectId) {
      entity.pos_x = pos.pos_x;
      entity.pos_y = pos.pos_y;
    }
  }
  return projectEntities(projectId);
}

// --- edge handlers --------------------------------------------------------

function findEdge(id: string): Edge {
  const edge = db.edges.find((e) => e.id === id);
  if (!edge) throw new ApiError(404, `Edge ${id} not found`, "not_found");
  return edge;
}

function createEdge(projectId: string, data: EdgeCreate): Edge {
  const edge: Edge = {
    id: uid("edge"),
    project_id: projectId,
    source_entity_id: data.source_entity_id,
    target_entity_id: data.target_entity_id,
    type: data.type,
    label: data.label ?? null,
    created_at: nowIso(),
  };
  db.edges.push(edge);
  return edge;
}

function updateEdge(id: string, data: EdgeUpdate): Edge {
  const edge = findEdge(id);
  edge.type = data.type;
  edge.label = data.label ?? null;
  if (data.reverse) {
    const s = edge.source_entity_id;
    edge.source_entity_id = edge.target_entity_id;
    edge.target_entity_id = s;
  }
  return edge;
}

function deleteEdge(id: string): undefined {
  findEdge(id);
  db.edges = db.edges.filter((e) => e.id !== id);
  return undefined;
}

// --- integration stubs ----------------------------------------------------

function stubConnection(projectId: string, body: unknown, id?: string): Connection {
  const data = (body ?? {}) as Partial<Connection>;
  const ts = nowIso();
  return {
    id: id ?? uid("conn"),
    project_id: projectId,
    connector_type: data.connector_type ?? "markdown",
    name: data.name ?? "Demo connection",
    config: data.config ?? {},
    use_for_grounding: data.use_for_grounding ?? false,
    auto_push_after_commit: data.auto_push_after_commit ?? false,
    created_at: ts,
    updated_at: ts,
  };
}

function requireSession(threadId: string): AgentSessionDetail {
  const session = findSession(threadId);
  if (!session) throw new ApiError(404, `Session ${threadId} not found`, "not_found");
  return session;
}

// --- streaming (agent) ----------------------------------------------------

export async function demoStream<TEvent>(
  path: string,
  body: unknown,
  onEvent: (event: TEvent) => void,
): Promise<void> {
  const emit = onEvent as (e: AgentEvent) => void;
  const messageMatch = matchPath("/api/projects/:id/agent/sessions/:tid/messages", path);
  const reviewMatch = matchPath("/api/projects/:id/agent/sessions/:tid/review", path);
  const skillMatch = matchPath("/api/projects/:id/agent/sessions/:tid/skills/:skill/run", path);

  if (messageMatch) return runAgentMessage(messageMatch.tid, body as { text: string }, emit);
  if (skillMatch) return runAgentMessage(skillMatch.tid, { text: `Run skill: ${skillMatch.skill}` }, emit);
  if (reviewMatch) return runAgentReview(reviewMatch.tid, body as AgentResumeRequest, emit);

  throw new ApiError(404, `Not Found (POST ${path} → demo stream)`, "not_found");
}

const STATUS_NODES = ["retrieve", "compose_lore", "extract_relationships", "review"];

/** Scripted draft: a rescued courier and the vault they're held in, grounded in
 * the seed's Session 1, the Sunken Chapel and the Hollow Court. The visitor's
 * message text only seeds the assistant's reply line — the draft is fixed so the
 * HITL review always has something coherent to approve. */
function scriptedDraft(): LoreDraft {
  return {
    entities: [
      {
        ref: "draft_courier",
        type: "npc",
        title: "Teodric the Lost",
        summary: "The missing Guild courier — alive, held beneath the Sunken Chapel.",
        fields: [
          { key: "role", value: "Guild Courier" },
          { key: "disposition", value: "captive ally" },
        ],
        grounded_in: ["sess_1", "fac_guild"],
      },
      {
        ref: "draft_vault",
        type: "location",
        title: "The Drowned Vault",
        summary: "A flooded chamber under the chapel where the Hollow Court keeps its prisoners.",
        fields: [{ key: "kind", value: "Dungeon" }],
        grounded_in: ["loc_ruins", "fac_shadow"],
      },
    ],
    relationships: [
      { op: "create", source_ref: "draft_courier", target_ref: "fac_guild", type: "member_of", reason: "He carries the Guild's seal.", grounded_in: ["fac_guild"] },
      { op: "create", source_ref: "draft_courier", target_ref: "draft_vault", type: "located_in", reason: "He is being held there.", grounded_in: [] },
      { op: "create", source_ref: "draft_vault", target_ref: "loc_ruins", type: "located_in", reason: "It lies beneath the chapel.", grounded_in: ["loc_ruins"] },
      { op: "create", source_ref: "draft_vault", target_ref: "fac_shadow", type: "owns", reason: "The Hollow Court controls it.", grounded_in: ["fac_shadow"] },
    ],
  };
}

async function streamTokens(text: string, emit: (e: AgentEvent) => void): Promise<void> {
  for (const word of text.split(" ")) {
    emit({ type: "token", text: word + " " });
    await delay(30);
  }
}

async function runAgentMessage(
  threadId: string,
  body: { text: string },
  emit: (e: AgentEvent) => void,
): Promise<void> {
  const session = requireSession(threadId);
  const text = body.text ?? "";
  pushMessage(session, { role: "user", text, attachments: [] });
  session.title = session.title || text.slice(0, 48);
  session.status = "running";

  for (const node of STATUS_NODES) {
    emit({ type: "status", node });
    await delay(150);
  }

  const reply =
    "I drafted the missing courier and the vault they're held in, tied to Session 1 and the Sunken Chapel. Review the changes below.";
  await streamTokens(reply, emit);
  pushMessage(session, { role: "assistant", text: reply, attachments: [] });

  const draft = scriptedDraft();
  const review: AgentReviewPayload = {
    draft,
    entity_edit_draft: null,
    warnings: [],
    input_tokens: 8200,
    output_tokens: 640,
  };
  session.review = review;
  session.status = "awaiting_review";
  session.input_tokens += review.input_tokens;
  session.output_tokens += review.output_tokens;

  emit({ type: "review", payload: review });
  emit({ type: "done", session: stripSession(session) });
}

async function runAgentReview(
  threadId: string,
  decision: AgentResumeRequest,
  emit: (e: AgentEvent) => void,
): Promise<void> {
  const session = requireSession(threadId);
  const review = session.review;

  if (decision.action === "revise") {
    emit({ type: "status", node: "compose_lore" });
    await delay(200);
    const note = "Revised the draft per your feedback — take another look.";
    await streamTokens(note, emit);
    pushMessage(session, { role: "assistant", text: note, attachments: [] });
    if (review) emit({ type: "review", payload: review });
    emit({ type: "done", session: stripSession(session) });
    return;
  }

  if (decision.action === "reject") {
    session.review = null;
    session.status = "rejected";
    const note = "Discarded — nothing was written to the campaign.";
    pushMessage(session, { role: "assistant", text: note, attachments: [] });
    emit({ type: "done", session: stripSession(session) });
    return;
  }

  // approve
  emit({ type: "status", node: "commit" });
  await delay(200);
  const draft = decision.draft ?? review?.draft ?? { entities: [], relationships: [] };
  const committed = commitDraft(session.project_id, draft);
  session.committed_entity_ids = committed;
  session.review = null;
  session.status = "committed";
  const note = `Committed ${committed.length} new entities to the campaign.`;
  pushMessage(session, { role: "assistant", text: note, attachments: [] });
  emit({ type: "done", session: stripSession(session) });
}

/** Writes an approved draft into the store: new entities get fresh ids, and
 * relationship refs are resolved against that ref→id map (falling back to
 * treating the ref as an existing entity id). */
function commitDraft(projectId: string, draft: LoreDraft): string[] {
  const refMap = new Map<string, string>();
  const committedIds: string[] = [];
  for (const de of draft.entities) {
    const fields = draftFieldsToEntityFields(de.fields);
    if (de.summary) {
      fields.unshift({
        key: "summary",
        field_type: "rich_text",
        value: { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: de.summary }] }] },
        show_on_card: true,
      });
    }
    const entity = createEntity(projectId, { type: de.type, title: de.title, fields });
    refMap.set(de.ref, entity.id);
    committedIds.push(entity.id);
  }
  for (const rel of draft.relationships) {
    if (rel.op && rel.op !== "create") continue;
    const source = refMap.get(rel.source_ref) ?? rel.source_ref;
    const target = refMap.get(rel.target_ref) ?? rel.target_ref;
    if (!findEntity(source) || !findEntity(target)) continue;
    createEdge(projectId, { source_entity_id: source, target_entity_id: target, type: rel.type, label: rel.reason });
  }
  return committedIds;
}
