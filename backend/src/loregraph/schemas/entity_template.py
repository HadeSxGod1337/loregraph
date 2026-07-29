"""Entity templates: a named preset that carries both a field skeleton (what
fields an entity of some type starts with) and a sheet layout (how those fields
are arranged for display and print).

Storage stays a generic bag of fields (see schemas/entity.py) — a template is a
*preset*, never an enforced schema: instantiated fields are freely edited or
removed afterwards. The layout is pure presentation and is NOT stored per
entity; only the template holds it.

WidgetType (how a field is drawn) is deliberately decoupled from FieldType (how
a value is stored): a NUMBER field can render as a plain input, a
stat-plus-modifier box, or a row of rating dots. That keeps rich sheets possible
without ever rigidifying the store.
"""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, model_validator

from loregraph.schemas.entity import FieldType, _coerce_field_value
from loregraph.schemas.formula import FormulaSyntaxError, parse_dependencies


class WidgetType(StrEnum):
    # v1 — arranging existing field types
    PLAIN = "plain"  # text/number/boolean as a labelled value
    RICH_TEXT = "rich_text"  # ProseMirror block
    TAG_CHIPS = "tag_chips"  # tag list as chips
    IMAGE = "image"  # attachment, or a text field holding a URL
    HEADING = "heading"  # decorative section heading (no field)
    DIVIDER = "divider"  # decorative rule (no field)
    # Rich widgets (phase 4) — still backed by a plain NUMBER field
    STAT_MODIFIER = "stat_modifier"  # score + derived modifier box
    DOTS = "dots"  # pips/dots rating (WoD-style)
    TRACKER = "tracker"  # current/max resource (HP…)
    # Formula-bound (phase 5) — not backed by a single field_key at all; see
    # Block.formula and schemas/formula.py.
    COMPUTED = "computed"  # value derived from other fields via a formula


# Widgets that render no field — field_key is not required (and ignored).
DECORATIVE_WIDGETS: frozenset[WidgetType] = frozenset(
    {WidgetType.HEADING, WidgetType.DIVIDER}
)

# Widgets whose value comes from Block.formula rather than a single
# field_key — validated separately in check_layout_references_fields.
FORMULA_WIDGETS: frozenset[WidgetType] = frozenset({WidgetType.COMPUTED})

# Which stored field types each single-field-bound widget can draw.
WIDGET_FIELD_TYPES: dict[WidgetType, frozenset[FieldType]] = {
    WidgetType.PLAIN: frozenset({FieldType.TEXT, FieldType.NUMBER, FieldType.BOOLEAN}),
    WidgetType.RICH_TEXT: frozenset({FieldType.RICH_TEXT}),
    WidgetType.TAG_CHIPS: frozenset({FieldType.TAG}),
    WidgetType.IMAGE: frozenset({FieldType.ATTACHMENT, FieldType.TEXT}),
    WidgetType.STAT_MODIFIER: frozenset({FieldType.NUMBER}),
    WidgetType.DOTS: frozenset({FieldType.NUMBER}),
    WidgetType.TRACKER: frozenset({FieldType.NUMBER}),
}

# Identifier bound to the stat_modifier block's own field value inside its
# `mod_formula` config — the one name a mod formula gets for free, on top of
# the template's field keys.
STAT_VALUE_IDENT = "value"

# D&D 5e ability-score modifier (PHB "Ability Scores and Modifiers"). Used
# when a stat_modifier block carries no explicit mod_formula, because that is
# the system the built-in Character template targets — every other system
# overrides it per block rather than the renderer assuming it.
DEFAULT_STAT_MOD_FORMULA = f"floor(({STAT_VALUE_IDENT} - 10) / 2)"

# Empty per-type default used at instantiation when a field def gives no
# explicit default_value. ATTACHMENT has no meaningful empty value, so an
# attachment field with no default is simply not created (the user adds it).
EMPTY_FIELD_DEFAULTS: dict[FieldType, Any] = {
    FieldType.TEXT: "",
    FieldType.RICH_TEXT: {"type": "doc", "content": [{"type": "paragraph"}]},
    FieldType.NUMBER: 0,
    FieldType.BOOLEAN: False,
    FieldType.TAG: [],
}


class TemplateFieldDef(BaseModel):
    key: str
    field_type: FieldType
    # None = use EMPTY_FIELD_DEFAULTS at instantiation (or skip, for attachment).
    default_value: Any = None
    label: str | None = None
    show_on_card: bool = False

    @model_validator(mode="after")
    def check_key_is_usable(self) -> Self:
        # A field key is an identity, not a caption: it is what blocks bind to,
        # what formulas reference and what an instantiated entity stores its
        # value under. A blank one produces a field nothing can address.
        if not self.key.strip():
            raise ValueError("field key must not be blank")
        return self

    @model_validator(mode="after")
    def check_default_matches_type(self) -> Self:
        if self.default_value is not None:
            self.default_value = _coerce_field_value(
                self.field_type, self.default_value
            )
        return self


def validate_field_keys_unique(field_defs: list[TemplateFieldDef]) -> None:
    """Two defs sharing a key silently collapse into one field on every
    instantiated entity (the store is keyed by field key) while the designer
    keeps showing both — the second one's type and default just disappear.
    Shared by EntityTemplateBase and SheetPresetBase."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for field_def in field_defs:
        if field_def.key in seen:
            duplicates.add(field_def.key)
        seen.add(field_def.key)
    if duplicates:
        raise ValueError(f"duplicate field key(s) {sorted(duplicates)!r}")


# id is a stable client-generated handle for drag-and-drop reordering/moves in
# the designer; the renderer keys off it too. Optional so older/hand-authored
# layouts still validate.
class Block(BaseModel):
    id: str | None = None
    widget: WidgetType
    # Required for single-field-bound widgets; omitted for decorative ones
    # and for COMPUTED (which uses `formula` instead — see FORMULA_WIDGETS).
    field_key: str | None = None
    # Required for widget == COMPUTED; a small expression (schemas/formula.py)
    # referencing other field_defs by key. Ignored for every other widget.
    formula: str | None = None
    label: str | None = None
    colspan: int = 1
    config: dict[str, Any] = {}


class Section(BaseModel):
    id: str | None = None
    title: str | None = None
    columns: int = 1
    blocks: list[Block] = []


class RegionKind(StrEnum):
    BAND = "band"  # flat row of blocks (portrait, key numbers…)
    COLUMNS = "columns"  # side-by-side containers, all visible at once
    TABS = "tabs"  # containers switched one-at-a-time via a tab bar


# A column (kind=COLUMNS) or a tab (kind=TABS) — both are just a named holder
# for stacked sections. Sharing one shape means the designer's block-level
# drag-and-drop (which only cares about section ids) needs no per-kind code.
class Container(BaseModel):
    id: str | None = None
    title: str | None = None
    sections: list[Section] = []


class Region(BaseModel):
    id: str | None = None
    name: str
    kind: RegionKind = RegionKind.BAND
    blocks: list[Block] = []  # populated only when kind == BAND
    containers: list[Container] = []  # populated only when kind != BAND

    @model_validator(mode="after")
    def check_shape_matches_kind(self) -> Self:
        if self.kind is RegionKind.BAND:
            if self.containers:
                raise ValueError("a band region cannot have containers")
        elif self.blocks:
            raise ValueError(f"a {self.kind} region cannot have top-level blocks")
        return self


class SheetLayout(BaseModel):
    regions: list[Region] = []

    def all_blocks(self) -> list[Block]:
        blocks: list[Block] = []
        for region in self.regions:
            blocks.extend(region.blocks)
            for container in region.containers:
                for section in container.sections:
                    blocks.extend(section.blocks)
        return blocks


def _validate_stat_mod_formula(block: Block, known_keys: set[str]) -> None:
    """`stat_modifier` draws a score plus a derived modifier. How that modifier
    is derived is system-specific (D&D halves the score, WoD has no such
    notion at all), so it lives in the block's config as a formula over
    STAT_VALUE_IDENT and the template's other fields — not as a rule baked
    into the renderer. Absent config means the D&D 5e default; see
    DEFAULT_STAT_MOD_FORMULA."""
    raw = block.config.get("mod_formula")
    if raw is None:
        return
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("mod_formula must be a non-empty formula string")
    try:
        dependencies = parse_dependencies(raw)
    except FormulaSyntaxError as exc:
        raise ValueError(f"invalid mod_formula {raw!r}: {exc}") from exc
    unknown = dependencies - known_keys - {STAT_VALUE_IDENT}
    if unknown:
        raise ValueError(
            f"mod_formula {raw!r} references unknown field(s) {sorted(unknown)!r}"
        )


def validate_blocks_reference_fields(
    blocks: list[Block], field_defs: list[TemplateFieldDef]
) -> None:
    """Shared by EntityTemplateBase.layout (a full SheetLayout) and
    SheetPresetBase.section (a single Section) — both ultimately validate a
    flat list of blocks against a template's/preset's own field_defs. Raises
    ValueError (Pydantic wraps it into a 422) on the first violation."""
    by_key = {f.key: f.field_type for f in field_defs}
    for block in blocks:
        if block.widget is WidgetType.STAT_MODIFIER:
            _validate_stat_mod_formula(block, set(by_key))
        if block.widget in DECORATIVE_WIDGETS:
            continue
        if block.widget in FORMULA_WIDGETS:
            if not block.formula:
                raise ValueError(f"widget {block.widget!r} requires a formula")
            try:
                dependencies = parse_dependencies(block.formula)
            except FormulaSyntaxError as exc:
                raise ValueError(f"invalid formula {block.formula!r}: {exc}") from exc
            unknown = dependencies - by_key.keys()
            if unknown:
                raise ValueError(
                    f"formula {block.formula!r} references unknown field(s) "
                    f"{sorted(unknown)!r}"
                )
            continue
        if block.field_key is None:
            raise ValueError(f"widget {block.widget!r} requires a field_key")
        field_type = by_key.get(block.field_key)
        if field_type is None:
            raise ValueError(
                f"layout block references unknown field {block.field_key!r}"
            )
        allowed = WIDGET_FIELD_TYPES[block.widget]
        if field_type not in allowed:
            raise ValueError(
                f"widget {block.widget!r} cannot render a {field_type!r} field "
                f"({block.field_key!r})"
            )


class EntityTemplateBase(BaseModel):
    name: str
    entity_type: str
    icon: str | None = None
    field_defs: list[TemplateFieldDef] = []
    layout: SheetLayout = SheetLayout()
    external_embed: "ExternalEmbedDef | None" = None

    @model_validator(mode="after")
    def check_layout_references_fields(self) -> Self:
        validate_field_keys_unique(self.field_defs)
        validate_blocks_reference_fields(self.layout.all_blocks(), self.field_defs)
        return self


class ExternalEmbedDef(BaseModel):
    """Declares that this template's entities carry a live sheet from an
    external service, embedded from a URL kept in one of their text fields
    (e.g. LongStoryShort). Generic on purpose — provider is just a registry
    key the frontend resolves to an embed-URL builder."""

    provider: str
    url_field: str


class EntityTemplateCreate(EntityTemplateBase):
    pass


class EntityTemplateUpdate(EntityTemplateBase):
    pass


class EntityTemplateOut(EntityTemplateBase):
    id: str
    # None for built-in templates (defined in code, not stored per project).
    project_id: str | None = None
    is_builtin: bool = False


class TemplateInstantiate(BaseModel):
    """Body for creating an entity from a template — the only per-instance
    input is its title; fields come pre-filled from the template's defaults."""

    title: str


EntityTemplateBase.model_rebuild()
