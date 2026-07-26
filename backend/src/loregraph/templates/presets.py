"""Built-in sheet presets, defined as data (not seeded into the DB) — same
split as templates/builtins.py: merged in above the store by
SheetPresetService.list_presets, read-only, a DM duplicates one to get an
editable project preset.

Each preset is dropped whole into a template's layout by the designer
(insertPreset in layoutOps.ts): its field_defs merge into the template's own
(existing keys win, so re-dropping a preset never duplicates a field), and
its `section` is appended to whichever container the DM dropped it on.
"""

from loregraph.schemas.entity import FieldType
from loregraph.schemas.entity_template import (
    Block,
    Section,
    TemplateFieldDef,
    WidgetType,
)
from loregraph.schemas.sheet_preset import SheetPresetOut


def _num(key: str, label: str) -> TemplateFieldDef:
    return TemplateFieldDef(key=key, field_type=FieldType.NUMBER, label=label)


def _bool(key: str, label: str) -> TemplateFieldDef:
    return TemplateFieldDef(key=key, field_type=FieldType.BOOLEAN, label=label)


def _preset(
    *, id: str, name: str, field_defs: list[TemplateFieldDef], section: Section
) -> SheetPresetOut:
    return SheetPresetOut(
        id=id,
        project_id=None,
        is_builtin=True,
        name=name,
        field_defs=field_defs,
        section=section,
    )


def _ability_skill_preset() -> SheetPresetOut:
    # Ловкость (dex) as the worked example — check, save, and its three
    # skills, every value a COMPUTED formula over the ability score plus an
    # optional proficiency bonus. See templates/builtins.py's Character
    # template for the full six-ability version this preset is a slice of.
    return _preset(
        id="preset_ability_skills",
        name="Характеристика + навыки (D&D)",
        field_defs=[
            _num("dex", "Ловкость"),
            _num("proficiency", "Бонус владения"),
            _bool("prof_save_dex", "Спасбросок: Ловкость (владение)"),
            _bool("prof_acrobatics", "Акробатика (владение)"),
            _bool("prof_sleight_of_hand", "Ловкость рук (владение)"),
            _bool("prof_stealth", "Скрытность (владение)"),
        ],
        section=Section(
            title="Ловкость",
            blocks=[
                # Empty label on purpose: the section is already titled
                # "Ловкость", a box captioned the same read as "Ловкость /
                # Ловкость". Without this block there is nowhere to type the
                # score every formula below depends on.
                Block(widget=WidgetType.STAT_MODIFIER, field_key="dex", label=""),
                Block(
                    widget=WidgetType.COMPUTED,
                    label="Проверка",
                    formula="floor((dex - 10) / 2)",
                ),
                Block(
                    widget=WidgetType.COMPUTED,
                    label="Спасбросок",
                    formula=(
                        "floor((dex - 10) / 2) + (prof_save_dex ? proficiency : 0)"
                    ),
                    config={"toggleable": ["prof_save_dex"]},
                ),
                Block(
                    widget=WidgetType.COMPUTED,
                    label="Акробатика",
                    formula=(
                        "floor((dex - 10) / 2) + (prof_acrobatics ? proficiency : 0)"
                    ),
                    config={"toggleable": ["prof_acrobatics"]},
                ),
                Block(
                    widget=WidgetType.COMPUTED,
                    label="Ловкость рук",
                    formula=(
                        "floor((dex - 10) / 2) + "
                        "(prof_sleight_of_hand ? proficiency : 0)"
                    ),
                    config={"toggleable": ["prof_sleight_of_hand"]},
                ),
                Block(
                    widget=WidgetType.COMPUTED,
                    label="Скрытность",
                    formula=(
                        "floor((dex - 10) / 2) + (prof_stealth ? proficiency : 0)"
                    ),
                    config={"toggleable": ["prof_stealth"]},
                ),
            ],
        ),
    )


def _resource_preset() -> SheetPresetOut:
    return _preset(
        id="preset_resource",
        name="Ресурс (текущее / макс)",
        field_defs=[
            _num("resource_current", "Ресурс (текущее)"),
            _num("resource_max", "Ресурс (макс.)"),
        ],
        section=Section(
            title="Ресурс",
            blocks=[
                Block(
                    widget=WidgetType.TRACKER,
                    field_key="resource_current",
                    label="Ресурс",
                    config={"max_field": "resource_max"},
                )
            ],
        ),
    )


def _checklist_preset() -> SheetPresetOut:
    items = [
        ("checklist_item_1", "Пункт 1"),
        ("checklist_item_2", "Пункт 2"),
        ("checklist_item_3", "Пункт 3"),
    ]
    return _preset(
        id="preset_checklist",
        name="Список с чекбоксами",
        field_defs=[_bool(key, label) for key, label in items],
        section=Section(
            title="Список",
            blocks=[
                Block(widget=WidgetType.PLAIN, field_key=key, label=label)
                for key, label in items
            ],
        ),
    )


def builtin_presets() -> list[SheetPresetOut]:
    """The shipped, read-only presets, in display order."""
    return [_ability_skill_preset(), _resource_preset(), _checklist_preset()]
