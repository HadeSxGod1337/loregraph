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

export interface Attachment {
  id: string;
  entity_id: string;
  url: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}
