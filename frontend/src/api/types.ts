export type FieldType = "text" | "rich_text" | "number" | "tag" | "attachment";

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

export type FieldValue = string | number | string[] | AttachmentRef | ProseMirrorDoc;

export interface EntityField {
  key: string;
  field_type: FieldType;
  value: FieldValue;
  show_on_card: boolean;
}

export interface Entity {
  id: string;
  project_id: string;
  type: string;
  title: string;
  fields: EntityField[];
  icon: AttachmentRef | null;
  created_at: string;
  updated_at: string;
}

export interface EntityCreate {
  type: string;
  title: string;
  fields: EntityField[];
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
