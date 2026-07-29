"""Sheet presets: a reusable bundle of field defs + one ready-made Section,
dragged whole into a template's layout in the designer (see
templates/presets.py for the shipped built-ins, TemplateDesigner.tsx for the
insertion UI). Same builtin-in-code + project-scoped-in-db split as
EntityTemplate (templates/builtins.py / entity_template_service.py) — kept as
a parallel, not-yet-shared implementation on purpose: this is only the
second occurrence of that pattern, and CLAUDE.md's DRY rule reserves
abstraction for a third.
"""

from typing import Self

from pydantic import BaseModel, model_validator

from loregraph.schemas.entity_template import (
    Section,
    TemplateFieldDef,
    validate_blocks_reference_fields,
    validate_field_keys_unique,
)


class SheetPresetBase(BaseModel):
    name: str
    field_defs: list[TemplateFieldDef] = []
    section: Section

    @model_validator(mode="after")
    def check_section_references_fields(self) -> Self:
        validate_field_keys_unique(self.field_defs)
        validate_blocks_reference_fields(self.section.blocks, self.field_defs)
        return self


class SheetPresetCreate(SheetPresetBase):
    pass


class SheetPresetOut(SheetPresetBase):
    id: str
    # None for built-in presets (defined in code, not stored per project).
    project_id: str | None = None
    is_builtin: bool = False
