export type FieldType =
  | "text"
  | "rich_text"
  | "number"
  | "boolean"
  | "tag"
  | "attachment";

export const DEFAULT_ENTITY_TYPES = [
  "npc",
  "location",
  "faction",
  "item",
  "session",
] as const;

export interface AttachmentRef {
  attachment_id: string;
  url: string;
}

export interface ProseMirrorDoc {
  type: "doc";
  content?: unknown[];
  [key: string]: unknown;
}

export type FieldValue =
  | string
  | number
  | boolean
  | string[]
  | AttachmentRef
  | ProseMirrorDoc;

export interface EntityField {
  key: string;
  field_type: FieldType;
  value: FieldValue;
  show_on_card: boolean;
  /** Whitelist for limited player access: shown to players only when true. */
  visible_to_players?: boolean;
}

export interface Entity {
  id: string;
  project_id: string;
  type: string;
  title: string;
  fields: EntityField[];
  template_id: string | null;
  icon: AttachmentRef | null;
  /** NULL = auto-layout should place this node; set = the user dragged it. */
  pos_x: number | null;
  pos_y: number | null;
  /** Whether the whole party can see this entity. */
  revealed_to_players: boolean;
  /** The separate text the DM wrote for players (ProseMirror doc). */
  player_text: ProseMirrorDoc | null;
  created_at: string;
  updated_at: string;
}

/** Everything about what players see for an entity, in one write. */
export interface EntityPlayerViewUpdate {
  revealed_to_players: boolean;
  player_text: ProseMirrorDoc | null;
  visible_field_keys: string[];
}

export interface Player {
  id: string;
  project_id: string;
  name: string;
  token_prefix: string;
  revoked: boolean;
  last_seen_at: string | null;
  note_count: number;
  play_url: string | null;
  created_at: string;
  updated_at: string;
}

/** Returned once, right after invite or rotate — the only time the raw token
 * and full link exist. */
export interface PlayerCreated extends Player {
  token: string;
}

export interface PlayerNote {
  id: string;
  entity_id: string;
  author_name: string;
  is_own: boolean;
  is_public: boolean;
  body: ProseMirrorDoc;
  created_at: string;
  updated_at: string;
}

// --- player-facing (the /play view) ---

export interface PlaySession {
  player_id: string;
  project_id: string;
  project_name: string;
  name: string;
}

/** An entity as a player sees it — only what the DM revealed. */
export interface PlayerEntity {
  id: string;
  type: string;
  title: string;
  icon: AttachmentRef | null;
  player_text: ProseMirrorDoc | null;
  fields: EntityField[];
  pos_x: number | null;
  pos_y: number | null;
}

export interface PlayerSubgraph {
  nodes: PlayerEntity[];
  edges: Edge[];
}

export interface PlayerNoteWrite {
  body: ProseMirrorDoc;
  is_public: boolean;
}

export interface EntityCreate {
  type: string;
  title: string;
  fields: EntityField[];
  template_id?: string | null;
}

export type EntityUpdate = EntityCreate;

export interface Edge {
  id: string;
  project_id: string;
  source_entity_id: string;
  target_entity_id: string;
  type: string;
  label: string | null;
  created_at: string;
}

export interface EdgeCreate {
  source_entity_id: string;
  target_entity_id: string;
  type: string;
  label?: string | null;
}

export interface EdgeUpdate {
  type: string;
  label?: string | null;
  reverse?: boolean;
}

export interface Subgraph {
  nodes: Entity[];
  edges: Edge[];
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  agent_instructions: string | null;
  /** World size, populated by the list endpoint (0 on single-project reads). */
  entity_count: number;
  edge_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  agent_instructions?: string | null;
}

export type ProjectUpdate = ProjectCreate;

// Matches backend schemas/project_transfer.py — used verbatim for both
// export (download) and import (upload) so the two stay a single contract.
export interface ProjectExport {
  format_version: number;
  name: string;
  description: string | null;
  entities: {
    id: string;
    type: string;
    title: string;
    fields: EntityField[];
    icon_attachment_id: string | null;
    pos_x: number | null;
    pos_y: number | null;
    // Optional: files exported before limited player access existed have
    // neither, and import treats them as all-hidden.
    revealed_to_players?: boolean;
    player_text?: ProseMirrorDoc | null;
  }[];
  edges: {
    source_entity_id: string;
    target_entity_id: string;
    type: string;
    label: string | null;
  }[];
  attachments: {
    id: string;
    entity_id: string;
    original_filename: string;
    stored_filename: string;
    content_type: string;
    data_base64: string;
  }[];
}

// --- Entity templates (mirror backend schemas/entity_template.py) ---

export type WidgetType =
  | "plain"
  | "rich_text"
  | "tag_chips"
  | "image"
  | "heading"
  | "divider"
  | "stat_modifier"
  | "dots"
  | "tracker"
  | "computed";

export interface TemplateFieldDef {
  key: string;
  field_type: FieldType;
  default_value?: FieldValue | null;
  label?: string | null;
  show_on_card: boolean;
}

export interface SheetBlock {
  /** Stable handle for drag-and-drop in the designer (client-generated). */
  id?: string | null;
  widget: WidgetType;
  field_key?: string | null;
  /** widget === "computed" only — see components/sheet/widgets/formula.ts. */
  formula?: string | null;
  label?: string | null;
  colspan: number;
  config: Record<string, unknown>;
}

export interface SheetSection {
  id?: string | null;
  title?: string | null;
  columns: number;
  blocks: SheetBlock[];
}

export type RegionKind = "band" | "columns" | "tabs";

/** A column (kind="columns") or a tab (kind="tabs") — both just hold
 * stacked sections; which one it renders as is the parent Region's kind. */
export interface SheetContainer {
  id?: string | null;
  title?: string | null;
  sections: SheetSection[];
}

export interface SheetRegion {
  id?: string | null;
  name: string;
  kind: RegionKind;
  /** Populated only when kind === "band". */
  blocks: SheetBlock[];
  /** Populated only when kind !== "band". */
  containers: SheetContainer[];
}

export interface SheetLayout {
  regions: SheetRegion[];
}

export interface ExternalEmbedDef {
  provider: string;
  url_field: string;
}

export interface EntityTemplate {
  id: string;
  project_id: string | null;
  is_builtin: boolean;
  name: string;
  entity_type: string;
  icon: string | null;
  field_defs: TemplateFieldDef[];
  layout: SheetLayout;
  external_embed: ExternalEmbedDef | null;
}

export type EntityTemplateCreate = Omit<
  EntityTemplate,
  "id" | "project_id" | "is_builtin"
>;

export type EntityTemplateUpdate = EntityTemplateCreate;

// --- Sheet presets (mirror backend schemas/sheet_preset.py) ---

export interface SheetPreset {
  id: string;
  project_id: string | null;
  is_builtin: boolean;
  name: string;
  field_defs: TemplateFieldDef[];
  section: SheetSection;
}

export type SheetPresetCreate = Omit<
  SheetPreset,
  "id" | "project_id" | "is_builtin"
>;

export interface Attachment {
  id: string;
  entity_id: string;
  url: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export type KnowledgeSourceStatus = "pending" | "processing" | "ready" | "failed";

export interface KnowledgeSource {
  id: string;
  project_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  status: KnowledgeSourceStatus;
  error: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface UsageRollupRow {
  node: string;
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
}

// --- Integrations / Connections ---

export interface ConnectorType {
  connector_type: string;
  capabilities: string[];
}

export interface Connection {
  id: string;
  project_id: string;
  connector_type: string;
  name: string;
  config: Record<string, unknown>;
  use_for_grounding: boolean;
  auto_push_after_commit: boolean;
  created_at: string;
  updated_at: string;
}

export type ConnectionCreate = Pick<
  Connection,
  "connector_type" | "name" | "config" | "use_for_grounding" | "auto_push_after_commit"
>;

export type ConnectionUpdate = Pick<
  Connection,
  "name" | "config" | "use_for_grounding" | "auto_push_after_commit"
>;

export interface ExportPreviewItem {
  entity_id: string;
  title: string;
  action: "create" | "update" | "skip";
  target: string;
  rendered: string | null;
}

export interface ExportPreview {
  items: ExportPreviewItem[];
}

export interface ItemError {
  ref: string;
  code: string;
  detail: string;
}

export interface ExportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: ItemError[];
}

export interface ImportedItem {
  entity_id: string;
  title: string;
  action: "created" | "updated";
}

/** Counts alone don't say who came in when a whole party is imported at
 * once, so an import also names what it touched. */
export interface ImportResult extends ExportResult {
  items: ImportedItem[];
}

export type ExportRequest = { entity_ids?: string[] };

export type ImportRequest = { payload?: Record<string, unknown> };

export interface ProbeResult {
  ok: boolean;
  detail_code: string;
  info: Record<string, string>;
}

export type UpdateMode = "ask" | "auto" | "never";

export interface UpdatePreferences {
  mode: UpdateMode;
  skipped_versions: string[];
}

export interface UpdateStatus {
  current_version: string;
  git_available: boolean;
  worktree_dirty: boolean;
  latest_version: string | null;
  update_available: boolean;
  changelog: string | null;
  checked_at: string | null;
  preferences: UpdatePreferences;
}

