import type { EntityTemplate, EntityTemplateCreate } from "../../../api/types";

/** Strip a fetched template down to an editable draft (drops id/builtin
 * metadata). Used both for editing a user template and duplicating a built-in
 * one into a new project template. */
export function toDraft(template: EntityTemplate): EntityTemplateCreate {
  return {
    name: template.name,
    entity_type: template.entity_type,
    icon: template.icon,
    field_defs: template.field_defs,
    layout: template.layout,
    external_embed: template.external_embed,
  };
}

export function emptyDraft(): EntityTemplateCreate {
  return {
    name: "",
    entity_type: "",
    icon: null,
    field_defs: [],
    layout: { regions: [] },
    external_embed: null,
  };
}
