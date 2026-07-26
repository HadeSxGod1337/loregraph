"""Built-in entity templates, defined as data (not seeded into the DB).

Merged in above the store by EntityTemplateService.list_templates, they are
read-only: a DM duplicates one to get an editable project template. The
Character template's field keys deliberately mirror the LongStoryShort importer
(connectors/longstoryshort/parser.py) so imported party members and
template-created ones share the same field vocabulary — including
`character_sheet_url`, which drives the live LSS embed via `external_embed`.

The Character template's "Способности и навыки" region is also the reference
example for COMPUTED widgets: every skill/save is a formula
(schemas/formula.py) over an ability score plus an optional proficiency
bonus, never a value stored on the entity itself.
"""

from loregraph.schemas.entity import FieldType
from loregraph.schemas.entity_template import (
    Block,
    Container,
    EntityTemplateOut,
    ExternalEmbedDef,
    Region,
    RegionKind,
    Section,
    SheetLayout,
    TemplateFieldDef,
    WidgetType,
)


def _text(key: str, label: str, *, show_on_card: bool = False) -> TemplateFieldDef:
    return TemplateFieldDef(
        key=key, field_type=FieldType.TEXT, label=label, show_on_card=show_on_card
    )


def _num(key: str, label: str, *, show_on_card: bool = False) -> TemplateFieldDef:
    return TemplateFieldDef(
        key=key, field_type=FieldType.NUMBER, label=label, show_on_card=show_on_card
    )


def _bool(key: str, label: str) -> TemplateFieldDef:
    return TemplateFieldDef(key=key, field_type=FieldType.BOOLEAN, label=label)


def _rich(key: str, label: str) -> TemplateFieldDef:
    return TemplateFieldDef(key=key, field_type=FieldType.RICH_TEXT, label=label)


def _tag(key: str, label: str, *, show_on_card: bool = False) -> TemplateFieldDef:
    return TemplateFieldDef(
        key=key, field_type=FieldType.TAG, label=label, show_on_card=show_on_card
    )


def _plain(field_key: str, *, colspan: int = 1) -> Block:
    return Block(widget=WidgetType.PLAIN, field_key=field_key, colspan=colspan)


def _tracker(field_key: str, label: str, *, max_field: str | None = None) -> Block:
    config: dict[str, object] = {}
    if max_field is not None:
        config["max_field"] = max_field
    return Block(
        widget=WidgetType.TRACKER, field_key=field_key, label=label, config=config
    )


def _rich_block(field_key: str) -> Block:
    return Block(widget=WidgetType.RICH_TEXT, field_key=field_key)


def _tag_block(field_key: str) -> Block:
    return Block(widget=WidgetType.TAG_CHIPS, field_key=field_key)


def _image_block(field_key: str) -> Block:
    return Block(widget=WidgetType.IMAGE, field_key=field_key)


def _template(
    *,
    id: str,
    name: str,
    entity_type: str,
    icon: str | None = None,
    field_defs: list[TemplateFieldDef],
    layout: SheetLayout,
    external_embed: ExternalEmbedDef | None = None,
) -> EntityTemplateOut:
    return EntityTemplateOut(
        id=id,
        project_id=None,
        is_builtin=True,
        name=name,
        entity_type=entity_type,
        icon=icon,
        field_defs=field_defs,
        layout=layout,
        external_embed=external_embed,
    )


# --- Character: ability/skill computed widgets ----------------------------

# (ability key, label) in SRD order; also the field_defs key for the score.
_ABILITIES: list[tuple[str, str]] = [
    ("str", "Сила"),
    ("dex", "Ловкость"),
    ("con", "Телосложение"),
    ("int", "Интеллект"),
    ("wis", "Мудрость"),
    ("cha", "Харизма"),
]

# Skills per governing ability (SRD 5e list); con has none.
_SKILLS: dict[str, list[tuple[str, str]]] = {
    "str": [("athletics", "Атлетика")],
    "dex": [
        ("acrobatics", "Акробатика"),
        ("sleight_of_hand", "Ловкость рук"),
        ("stealth", "Скрытность"),
    ],
    "con": [],
    "int": [
        ("investigation", "Анализ"),
        ("history", "История"),
        ("arcana", "Магия"),
        ("nature", "Природа"),
        ("religion", "Религия"),
    ],
    "wis": [
        ("perception", "Восприятие"),
        ("survival", "Выживание"),
        ("medicine", "Медицина"),
        ("insight", "Проницательность"),
        ("animal_handling", "Уход за животными"),
    ],
    "cha": [
        ("performance", "Выступление"),
        ("intimidation", "Запугивание"),
        ("deception", "Обман"),
        ("persuasion", "Убеждение"),
    ],
}

_LEFT_COLUMN_ABILITIES = frozenset({"str", "con", "int"})


def _ability_bool_defs() -> list[TemplateFieldDef]:
    defs: list[TemplateFieldDef] = []
    for ability_key, ability_label in _ABILITIES:
        defs.append(
            _bool(
                f"prof_save_{ability_key}",
                f"Спасбросок: {ability_label} (владение)",
            )
        )
        for skill_key, skill_label in _SKILLS[ability_key]:
            defs.append(_bool(f"prof_{skill_key}", f"{skill_label} (владение)"))
    return defs


def _check_block(ability_key: str) -> Block:
    # Ability checks are never proficiency-gated in 5e — plain modifier.
    return Block(
        widget=WidgetType.COMPUTED,
        label="Проверка",
        formula=f"floor(({ability_key} - 10) / 2)",
    )


def _save_block(ability_key: str) -> Block:
    prof_key = f"prof_save_{ability_key}"
    return Block(
        widget=WidgetType.COMPUTED,
        label="Спасбросок",
        formula=f"floor(({ability_key} - 10) / 2) + ({prof_key} ? proficiency : 0)",
        config={"toggleable": [prof_key]},
    )


def _skill_block(ability_key: str, skill_key: str, label: str) -> Block:
    prof_key = f"prof_{skill_key}"
    return Block(
        widget=WidgetType.COMPUTED,
        label=label,
        formula=f"floor(({ability_key} - 10) / 2) + ({prof_key} ? proficiency : 0)",
        config={"toggleable": [prof_key]},
    )


def _score_block(ability_key: str) -> Block:
    """The editable ability score itself. Without it every derived row below
    is stuck at the score-0 modifier with nowhere to type the real value.

    The label is deliberately empty: the section around it already carries
    the ability's name, and repeating it inside the box read as "Сила / Сила".
    """
    return Block(widget=WidgetType.STAT_MODIFIER, field_key=ability_key, label="")


def _ability_section(ability_key: str, ability_label: str) -> Section:
    blocks = [
        _score_block(ability_key),
        _check_block(ability_key),
        _save_block(ability_key),
    ]
    blocks.extend(
        _skill_block(ability_key, skill_key, skill_label)
        for skill_key, skill_label in _SKILLS[ability_key]
    )
    return Section(title=ability_label, blocks=blocks)


def _ability_skill_region() -> Region:
    left = [
        _ability_section(key, label)
        for key, label in _ABILITIES
        if key in _LEFT_COLUMN_ABILITIES
    ]
    right = [
        _ability_section(key, label)
        for key, label in _ABILITIES
        if key not in _LEFT_COLUMN_ABILITIES
    ]
    return Region(
        name="Способности и навыки",
        kind=RegionKind.COLUMNS,
        containers=[Container(sections=left), Container(sections=right)],
    )


def _character() -> EntityTemplateOut:
    ability_defs = [_num(key, label) for key, label in _ABILITIES]
    return _template(
        id="builtin_character",
        name="Персонаж",
        entity_type="party_member",
        field_defs=[
            _text("avatar_url", "Портрет (URL)"),
            _text("class", "Класс", show_on_card=True),
            _text("subclass", "Архетип"),
            _text("ancestry", "Происхождение", show_on_card=True),
            _text("background", "Предыстория"),
            _text("alignment", "Мировоззрение"),
            _num("level", "Уровень", show_on_card=True),
            _num("experience", "Опыт"),
            _num("proficiency", "Бонус владения"),
            _num("ac", "Класс доспеха"),
            _num("speed", "Скорость"),
            _num("hp", "Текущие хиты"),
            _num("max_hp", "Макс. хиты"),
            *ability_defs,
            *_ability_bool_defs(),
            _rich("personality", "Черты характера"),
            _rich("ideals", "Идеалы"),
            _rich("bonds", "Привязанности"),
            _rich("flaws", "Слабости"),
            _rich("backstory", "Предыстория персонажа"),
            _rich("allies", "Союзники и организации"),
            _rich("quests", "Цели и задачи"),
            _text("character_sheet_url", "Ссылка на лист"),
        ],
        layout=SheetLayout(
            regions=[
                Region(
                    name="Шапка",
                    kind=RegionKind.BAND,
                    blocks=[
                        _image_block("avatar_url"),
                        _plain("level"),
                        _plain("ac"),
                        _tracker("hp", "Хиты", max_field="max_hp"),
                        _plain("speed"),
                        _plain("proficiency"),
                    ],
                ),
                Region(
                    name="Владения",
                    kind=RegionKind.BAND,
                    blocks=[
                        _plain("class"),
                        _plain("subclass"),
                        _plain("ancestry"),
                        _plain("background"),
                        _plain("alignment"),
                        _plain("max_hp"),
                        _plain("experience"),
                    ],
                ),
                _ability_skill_region(),
                Region(
                    name="Биография",
                    kind=RegionKind.TABS,
                    containers=[
                        Container(
                            title="Личность",
                            sections=[
                                Section(
                                    blocks=[
                                        _rich_block("personality"),
                                        _rich_block("ideals"),
                                        _rich_block("bonds"),
                                        _rich_block("flaws"),
                                    ]
                                )
                            ],
                        ),
                        Container(
                            title="История",
                            sections=[
                                Section(
                                    blocks=[
                                        _rich_block("backstory"),
                                        _rich_block("allies"),
                                        _rich_block("quests"),
                                    ]
                                )
                            ],
                        ),
                    ],
                ),
            ],
        ),
        external_embed=ExternalEmbedDef(
            provider="longstoryshort", url_field="character_sheet_url"
        ),
    )


def _npc() -> EntityTemplateOut:
    return _template(
        id="builtin_npc",
        name="NPC",
        entity_type="npc",
        field_defs=[
            _text("role", "Роль", show_on_card=True),
            _text("faction", "Фракция"),
            _text("disposition", "Отношение"),
            _text("stat_block_ref", "Стат-блок (ссылка)"),
            _rich("appearance", "Внешность"),
            _rich("personality", "Характер"),
            _rich("secret", "Секрет"),
        ],
        layout=SheetLayout(
            regions=[
                Region(
                    name="Шапка",
                    kind=RegionKind.BAND,
                    blocks=[_plain("role"), _plain("faction"), _plain("disposition")],
                ),
                Region(
                    name="Обзор",
                    kind=RegionKind.TABS,
                    containers=[
                        Container(
                            title="Обзор",
                            sections=[
                                Section(
                                    blocks=[
                                        _rich_block("appearance"),
                                        _rich_block("personality"),
                                        _rich_block("secret"),
                                    ]
                                ),
                                Section(
                                    title="Механика",
                                    blocks=[_plain("stat_block_ref")],
                                ),
                            ],
                        )
                    ],
                ),
            ],
        ),
    )


def _location() -> EntityTemplateOut:
    return _template(
        id="builtin_location",
        name="Локация",
        entity_type="location",
        field_defs=[
            _text("region", "Регион", show_on_card=True),
            _text("loc_type", "Тип", show_on_card=True),
            _text("population", "Население"),
            _rich("description", "Описание"),
            _rich("points_of_interest", "Примечательные места"),
            _tag("inhabitants", "Обитатели"),
        ],
        layout=SheetLayout(
            regions=[
                Region(
                    name="Шапка",
                    kind=RegionKind.BAND,
                    blocks=[
                        _plain("region"),
                        _plain("loc_type"),
                        _plain("population"),
                    ],
                ),
                Region(
                    name="Обзор",
                    kind=RegionKind.TABS,
                    containers=[
                        Container(
                            title="Обзор",
                            sections=[
                                Section(
                                    blocks=[
                                        _rich_block("description"),
                                        _rich_block("points_of_interest"),
                                    ]
                                ),
                                Section(
                                    title="Обитатели",
                                    blocks=[_tag_block("inhabitants")],
                                ),
                            ],
                        )
                    ],
                ),
            ],
        ),
    )


def _faction() -> EntityTemplateOut:
    return _template(
        id="builtin_faction",
        name="Фракция",
        entity_type="faction",
        field_defs=[
            _text("leader", "Лидер", show_on_card=True),
            _text("headquarters", "Штаб-квартира"),
            _rich("description", "Описание"),
            _rich("goals", "Цели"),
            _tag("allies", "Союзники"),
            _tag("enemies", "Враги"),
        ],
        layout=SheetLayout(
            regions=[
                Region(
                    name="Шапка",
                    kind=RegionKind.BAND,
                    blocks=[_plain("leader"), _plain("headquarters")],
                ),
                Region(
                    name="Обзор",
                    kind=RegionKind.TABS,
                    containers=[
                        Container(
                            title="Обзор",
                            sections=[
                                Section(
                                    blocks=[
                                        _rich_block("description"),
                                        _rich_block("goals"),
                                    ]
                                ),
                                Section(
                                    title="Отношения",
                                    columns=2,
                                    blocks=[
                                        _tag_block("allies"),
                                        _tag_block("enemies"),
                                    ],
                                ),
                            ],
                        )
                    ],
                ),
            ],
        ),
    )


def builtin_templates() -> list[EntityTemplateOut]:
    """The shipped, read-only templates, in display order."""
    return [_character(), _npc(), _location(), _faction()]
