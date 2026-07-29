import copy

from loregraph.exceptions import (
    BuiltinTemplateReadOnlyError,
    EntityTemplateNotFoundError,
)
from loregraph.schemas.entity import EntityFieldIn
from loregraph.schemas.entity_template import (
    EMPTY_FIELD_DEFAULTS,
    EntityTemplateCreate,
    EntityTemplateOut,
    EntityTemplateUpdate,
)
from loregraph.storage.protocols import EntityTemplateStore
from loregraph.templates import builtin_templates


def template_to_fields(template: EntityTemplateOut) -> list[EntityFieldIn]:
    """Turn a template's field defs into a pre-filled field list for a new
    entity. A field with an explicit default_value uses it; otherwise it uses
    the empty default for its type. Attachment fields with no default are
    skipped — the user adds the file later. Values are deep-copied so instances
    never share a mutable default (rich_text doc / tag list)."""
    fields: list[EntityFieldIn] = []
    for field_def in template.field_defs:
        if field_def.default_value is not None:
            value = field_def.default_value
        elif field_def.field_type in EMPTY_FIELD_DEFAULTS:
            value = EMPTY_FIELD_DEFAULTS[field_def.field_type]
        else:
            continue
        fields.append(
            EntityFieldIn(
                key=field_def.key,
                field_type=field_def.field_type,
                value=copy.deepcopy(value),
                show_on_card=field_def.show_on_card,
            )
        )
    return fields


class EntityTemplateService:
    """Merges built-in templates (defined in code) with a project's own stored
    templates behind one interface. Built-ins are read-only: create/update/
    delete only ever touch project templates."""

    def __init__(self, store: EntityTemplateStore) -> None:
        self._store = store
        self._builtins = {t.id: t for t in builtin_templates()}

    async def list_templates(self, project_id: str) -> list[EntityTemplateOut]:
        user_templates = await self._store.list_for_project(project_id)
        return [*self._builtins.values(), *user_templates]

    async def default_for_entity_type(
        self, project_id: str, entity_type: str
    ) -> EntityTemplateOut | None:
        """The template a new entity of this type should be bound to when
        nobody picked one — an importer creating a party member, say.

        A project's own template wins over the built-in one: a DM who built a
        sheet for their system means it to be *the* sheet for that type. None
        when the type has no template at all, which is a valid answer (the
        entity is then a plain field list, as before).
        """
        for template in await self._store.list_for_project(project_id):
            if template.entity_type == entity_type:
                return template
        for builtin in self._builtins.values():
            if builtin.entity_type == entity_type:
                return builtin
        return None

    async def get_for_project(
        self, project_id: str, template_id: str
    ) -> EntityTemplateOut:
        builtin = self._builtins.get(template_id)
        if builtin is not None:
            return builtin
        template = await self._store.get(template_id)
        if template.project_id != project_id:
            # Wrong project for this id — 404, not 403 (same rule as entities).
            raise EntityTemplateNotFoundError(template_id)
        return template

    async def create(
        self, project_id: str, data: EntityTemplateCreate
    ) -> EntityTemplateOut:
        return await self._store.create(project_id, data)

    async def update(
        self, project_id: str, template_id: str, data: EntityTemplateUpdate
    ) -> EntityTemplateOut:
        if template_id in self._builtins:
            raise BuiltinTemplateReadOnlyError(template_id)
        await self.get_for_project(project_id, template_id)
        return await self._store.update(template_id, data)

    async def delete(self, project_id: str, template_id: str) -> None:
        if template_id in self._builtins:
            raise BuiltinTemplateReadOnlyError(template_id)
        await self.get_for_project(project_id, template_id)
        await self._store.delete(template_id)
