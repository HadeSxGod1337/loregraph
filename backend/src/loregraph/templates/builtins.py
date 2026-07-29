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

from functools import cache

from loregraph.schemas.entity import FieldType
from loregraph.schemas.entity_template import (
    DEFAULT_STAT_MOD_FORMULA,
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


def _rich_block(field_key: str, *, label: str | None = None, colspan: int = 1) -> Block:
    # label="" suppresses the caption entirely — for a section whose title
    # already names the field ("Снаряжение" over the equipment block).
    return Block(
        widget=WidgetType.RICH_TEXT, field_key=field_key, label=label, colspan=colspan
    )


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

# Short ability tags for skill rows ("Акробатика (Лов)") — the skills live in
# one flat list, so each row has to say which ability it derives from.
_ABILITY_SHORT: dict[str, str] = {
    "str": "Сил",
    "dex": "Лов",
    "con": "Тел",
    "int": "Инт",
    "wis": "Муд",
    "cha": "Хар",
}


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


def _save_block(ability_key: str, ability_label: str) -> Block:
    prof_key = f"prof_save_{ability_key}"
    return Block(
        widget=WidgetType.COMPUTED,
        label=ability_label,
        formula=f"floor(({ability_key} - 10) / 2) + ({prof_key} ? proficiency : 0)",
        # signed: a save bonus is a modifier — it is rolled *onto* a d20 and
        # reads "+3"/"-1". A computed total (see _passive_section) is not.
        config={"toggleable": [prof_key], "signed": True},
    )


def _skill_block(ability_key: str, skill_key: str, label: str) -> Block:
    prof_key = f"prof_{skill_key}"
    return Block(
        widget=WidgetType.COMPUTED,
        label=label,
        formula=f"floor(({ability_key} - 10) / 2) + ({prof_key} ? proficiency : 0)",
        config={"toggleable": [prof_key], "signed": True},
    )


def _scores_section() -> Section:
    """The six editable scores as one dense grid of boxes. Each box already
    shows its own modifier, which is the ability check — no separate row for
    it, the way a printed sheet does it."""
    return Section(
        title="Характеристики",
        blocks=[
            Block(
                widget=WidgetType.STAT_MODIFIER,
                field_key=key,
                label=label,
                # Spelled out rather than left to the renderer's fallback:
                # this template is D&D 5e, and a duplicated copy retargeted at
                # another system should show the DM what to change.
                config={"mod_formula": DEFAULT_STAT_MOD_FORMULA},
            )
            for key, label in _ABILITIES
        ],
    )


def _saves_section() -> Section:
    return Section(
        title="Спасброски",
        blocks=[_save_block(key, label) for key, label in _ABILITIES],
    )


def _skills_section() -> Section:
    """Every skill in one alphabetical list, each row tagged with its ability.

    Grouping skills under per-ability cards cost six card frames and six
    headings for eighteen rows of content, and pushed the sheet onto a second
    printed page. One list reads the same and fits.
    """
    blocks = [
        _skill_block(
            ability_key, skill_key, f"{skill_label} ({_ABILITY_SHORT[ability_key]})"
        )
        for ability_key, _ in _ABILITIES
        for skill_key, skill_label in _SKILLS[ability_key]
    ]
    blocks.sort(key=lambda block: (block.label or "").lower())
    return Section(title="Навыки", blocks=blocks)


def _passive_section() -> Section:
    return Section(
        title="Пассивные значения",
        blocks=[
            Block(
                widget=WidgetType.COMPUTED,
                label="Пассивная внимательность",
                formula=(
                    "10 + floor((wis - 10) / 2) + (prof_perception ? proficiency : 0)"
                ),
            )
        ],
    )


def _ability_skill_region() -> Region:
    return Region(
        name="Способности и навыки",
        kind=RegionKind.COLUMNS,
        containers=[
            Container(
                sections=[_scores_section(), _saves_section(), _passive_section()]
            ),
            Container(sections=[_skills_section()]),
        ],
    )


_COINS: list[tuple[str, str]] = [
    ("pp", "ПМ"),
    ("gp", "ЗМ"),
    ("ep", "ЭМ"),
    ("sp", "СМ"),
    ("cp", "ММ"),
]

_APPEARANCE: list[tuple[str, str]] = [
    ("age", "Возраст"),
    ("height", "Рост"),
    ("weight", "Вес"),
    ("eyes", "Глаза"),
    ("skin", "Кожа"),
    ("hair", "Волосы"),
]


def _combat_region() -> Region:
    """Everything the DM reaches for mid-fight, in the order a printed sheet
    puts it: what you swing, what it costs, what you carry."""
    return Region(
        name="Бой и снаряжение",
        kind=RegionKind.COLUMNS,
        containers=[
            Container(
                sections=[
                    Section(
                        title="Атаки",
                        blocks=[_rich_block("weapons"), _rich_block("attacks")],
                    ),
                    Section(
                        title="Заклинания",
                        columns=2,
                        blocks=[
                            _plain("caster_class"),
                            _plain("spell_ability"),
                            _plain("spell_save_dc"),
                            _plain("spell_attack"),
                            # Span the section: slots and the list itself go
                            # under the casting stats, as on a printed sheet.
                            _rich_block("spell_slots", label="", colspan=2),
                            _rich_block("spells", label="", colspan=2),
                        ],
                    ),
                    Section(
                        title="Хиты и кости",
                        columns=2,
                        blocks=[
                            _plain("temp_hp"),
                            _plain("hit_die"),
                            _plain("hit_dice_current"),
                            _plain("exhaustion"),
                        ],
                    ),
                ]
            ),
            Container(
                sections=[
                    Section(
                        title="Снаряжение", blocks=[_rich_block("equipment", label="")]
                    ),
                    Section(
                        title="Монеты",
                        columns=5,
                        blocks=[_plain(f"coins_{key}") for key, _ in _COINS],
                    ),
                    Section(
                        title="Настроенные предметы",
                        blocks=[_rich_block("attunements", label="")],
                    ),
                    Section(
                        title="Сокровища", blocks=[_rich_block("treasures", label="")]
                    ),
                ]
            ),
        ],
    )


def _features_region() -> Region:
    return Region(
        name="Умения и владения",
        kind=RegionKind.COLUMNS,
        containers=[
            Container(
                sections=[
                    Section(
                        title="Умения и способности",
                        blocks=[_rich_block("features", label="")],
                    ),
                    Section(
                        title="Ресурсы", blocks=[_rich_block("resources", label="")]
                    ),
                ]
            ),
            Container(
                sections=[
                    Section(
                        title="Дополнительные способности",
                        blocks=[_rich_block("extra_features", label="")],
                    ),
                    Section(
                        title="Прочие владения и языки",
                        blocks=[_rich_block("other_proficiencies", label="")],
                    ),
                ]
            ),
        ],
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
            _num("temp_hp", "Временные хиты"),
            _text("hit_die", "Кость хитов"),
            _num("hit_dice_current", "Осталось костей"),
            _num("exhaustion", "Истощение"),
            _bool("inspiration", "Вдохновение"),
            _text("player_name", "Имя игрока"),
            *ability_defs,
            *_ability_bool_defs(),
            _rich("weapons", "Оружие"),
            _rich("attacks", "Атаки и заклинания"),
            _rich("spells", "Заклинания"),
            _rich("spell_slots", "Ячейки заклинаний"),
            _rich("attunements", "Настроенные предметы"),
            _text("caster_class", "Класс заклинателя"),
            _text("spell_ability", "Базовая характеристика"),
            _text("spell_save_dc", "Сложность спасброска"),
            _text("spell_attack", "Бонус атаки"),
            _rich("equipment", "Снаряжение"),
            _rich("treasures", "Сокровища"),
            _rich("features", "Умения и способности"),
            _rich("extra_features", "Дополнительные способности"),
            _rich("other_proficiencies", "Прочие владения и языки"),
            _rich("resources", "Ресурсы"),
            *[_num(f"coins_{key}", label) for key, label in _COINS],
            _rich("personality", "Черты характера"),
            _rich("ideals", "Идеалы"),
            _rich("bonds", "Привязанности"),
            _rich("flaws", "Слабости"),
            _rich("backstory", "Предыстория персонажа"),
            _rich("allies", "Союзники и организации"),
            _rich("quests", "Цели и задачи"),
            _rich("notes", "Заметки"),
            *[_text(key, label) for key, label in _APPEARANCE],
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
                        _plain("player_name"),
                        _plain("max_hp"),
                        _plain("experience"),
                    ],
                ),
                _ability_skill_region(),
                _combat_region(),
                _features_region(),
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
                        Container(
                            title="Внешность",
                            sections=[
                                Section(
                                    columns=3,
                                    blocks=[_plain(key) for key, _ in _APPEARANCE],
                                )
                            ],
                        ),
                        Container(
                            title="Заметки",
                            sections=[Section(blocks=[_rich_block("notes", label="")])],
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


@cache
def builtin_templates() -> tuple[EntityTemplateOut, ...]:
    """The shipped, read-only templates, in display order.

    Built once per process, not once per request: EntityTemplateService is
    constructed per HTTP request, and the Character template alone is a few
    hundred validated Pydantic models (every skill row is a Block). A tuple
    of read-only templates is safe to share — nothing mutates them, and
    instantiation deep-copies the values it takes (template_to_fields).
    """
    return (_character(), _npc(), _location(), _faction())
