# Entity templates and character sheets

*Русская версия — [templates.md](templates.md).*

A template describes **which fields** an entity gets and **how they are laid
out** on its sheet. One template drives three surfaces at once: the compact
sheet in the graph drawer, the full sheet in the modal, and the printed page —
same layout, different density.

A template is a **starting point, not a schema**. Entity storage stays a free
bag of fields: after a template is applied, fields can be edited, added and
removed, and nothing breaks. The sheet never hides data — a field that no block,
no formula and no `max_field` refers to lands in the "Other fields" section at
the bottom of the sheet.

Where to find it: **Project settings → Templates** (the designer) and the
"Template" selector on the entity page / in the graph drawer.

---

## What a template is made of

```
Template
├── Fields (field_defs)   — what the data is and how it is stored
└── Layout                — how it looks
    └── Region            — band | columns | tabs
        ├── Blocks        — band regions only
        └── Containers    — a column (columns) or a tab (tabs)
            └── Section   — a titled card, N columns wide
                └── Block — one widget
```

### Fields

| Property        | Meaning                                                      |
| --------------- | ------------------------------------------------------------ |
| `key`           | Identifier. Blocks and formulas refer to it                  |
| `field_type`    | `text`, `rich_text`, `number`, `boolean`, `tag`, `attachment` |
| `label`         | Human caption (`key` is the fallback)                        |
| `default_value` | Value used when an entity is created from the template       |
| `show_on_card`  | Whether the field shows on the entity card in lists          |

Once a field has been saved its key is locked (a freshly added one is still
editable) — that removes the need to cascade renames through the layout and
every formula. Deleting a field something refers to is confirmed separately and
strips the referring blocks from the layout.

### Regions

| Kind      | What it is                                          | Good for                        |
| --------- | --------------------------------------------------- | ------------------------------- |
| `band`    | A flat row of blocks, no cards                      | Header, a strip of key numbers  |
| `columns` | Containers side by side, all visible at once        | Abilities and skills            |
| `tabs`    | Containers switched via a tab bar, one visible      | Biography, gear, notes          |

How many columns actually appear is decided by available width, not by a
setting: in a narrow drawer and on paper a `columns` region collapses to a
single column, and a `tabs` region unfolds into every tab stacked (paper and
drawers have nothing to switch with).

If a template's first region is a `band`, it renders as the **sheet header**:
portrait, name, type and a strip of key-number pills.

### Widgets

Widget type is deliberately decoupled from field type: the same number field can
be a plain input, an ability-score box, or a row of rating dots.

| Widget          | Field types           | Settings (`config`)                 |
| --------------- | --------------------- | ----------------------------------- |
| `plain`         | text, number, boolean | —                                   |
| `rich_text`     | rich_text             | —                                   |
| `tag_chips`     | tag                   | —                                   |
| `image`         | attachment, text(URL) | —                                   |
| `stat_modifier` | number                | —                                   |
| `dots`          | number                | `max` — how many pips (default 5)   |
| `tracker`       | number                | `max_field` — key of the max field  |
| `computed`      | —                     | `toggleable` — see below            |
| `heading`       | —                     | —                                   |
| `divider`       | —                     | —                                   |

`heading` and `divider` are decorative and need no field. `computed` is not
bound to a single field either: its value comes entirely from a formula.

An empty block label (`label: ""`) means "no caption here" on purpose, rather
than "fall back to the field's name". That is how the ability-score box inside a
section already titled "Strength" is built — otherwise it read as
"Strength / Strength".

---

## Formulas

The `computed` widget shows a value derived from other fields: an ability
modifier, a skill bonus including proficiency, armour class, carrying capacity.
The value itself is not editable — it is a derived number.

Formulas are deliberately **not** Python or JS: this is a small expression
language with its own parser, no `eval`, and no access to anything beyond the
current entity's fields.

### What you can write

**A field reference** is just its key: `str`, `proficiency`, `prof_stealth`.

**Numbers**: `10`, `2.5`.

**Operators**, strongest binding first:

| Group             | Operators                      | Example              |
| ----------------- | ------------------------------ | -------------------- |
| Grouping, call    | `( )`, `floor(x)`              | `floor((str-10)/2)`  |
| Unary             | `-x`, `!x`                     | `-penalty`           |
| Multiplicative    | `*`, `/`, `%`                  | `level * 2`          |
| Additive          | `+`, `-`                       | `dex + 10`           |
| Comparison        | `<`, `<=`, `>`, `>=`           | `level >= 5`         |
| Equality          | `==`, `!=`                     | `size == 1`          |
| And               | `&&`                           | `a && b`             |
| Or                | `\|\|`                         | `a \|\| b`           |
| Conditional       | `cond ? if_true : if_false`    | `prof ? bonus : 0`   |

**Functions** — exactly six: `floor`, `ceil`, `round`, `abs`, `min`, `max`.
`min` and `max` take any number of arguments, the rest take one.

### Evaluation rules

- **A missing or empty field is 0** (false in boolean context). The sheet of a
  half-filled entity shows a number, not an error.
- **A boolean field** is `1`/`0` in arithmetic; any non-zero number is true in
  boolean context.
- **Division by zero yields 0**, not infinity and not an error.
- A numeric result is displayed signed (`+3`, `-1`); a boolean result as
  `✓` / `—`.
- A formula may only reference **real fields**, never another `computed` block.
  That restriction is intentional: circular dependencies become impossible by
  construction, so no recompute graph is needed.

Every formula is checked twice: the designer flags syntax errors and unknown
keys as you type, and the backend rejects saving the template (422) if the
formula does not parse or refers to a key absent from `field_defs`.

### Proficiency toggles

The formula describes the arithmetic; `config.toggleable` decides which of its
**boolean** inputs get a checkbox right in the skill row:

```
formula:    floor((dex - 10) / 2) + (prof_stealth ? proficiency : 0)
toggleable: ["prof_stealth"]
```

That renders as "☐ Stealth +1" — tick the box and the bonus recomputes in place.
The checkboxes are editable while filling the sheet in; in read-only view and in
print they are visible but disabled.

### Examples

```python
# Ability modifier (D&D 5e)
floor((str - 10) / 2)

# A skill or save including proficiency
floor((dex - 10) / 2) + (prof_stealth ? proficiency : 0)

# Passive perception
10 + floor((wis - 10) / 2) + (prof_perception ? proficiency : 0)

# Unarmoured defense (monk/barbarian)
10 + floor((dex - 10) / 2) + floor((wis - 10) / 2)

# Dexterity to AC, capped as by medium armour
armor_base + min(2, floor((dex - 10) / 2))

# Carrying capacity
str * 15

# Expertise: proficiency counted twice
floor((cha - 10) / 2) + (prof_persuasion ? proficiency : 0) + (expertise_persuasion ? proficiency : 0)
```

---

## Presets

A preset is a ready-made piece of a sheet: a bundle of fields plus one section
of blocks. Drag it from the designer's palette into a column or tab and it is
inserted whole, fields included. If a field with the same key already exists in
the template, the existing one is reused — no duplicates.

Built-in presets:

- **Ability + skills (D&D)** — the ability-score box, check, save and skills as
  formulas; the reference example of how all of this fits together.
- **Resource (current / max)** — a tracker with a max field.
- **Checklist** — a set of boolean fields.

Any section can be saved as a project preset from the button in its header.
Built-in presets are read-only (editing one → 409); user presets live inside a
project.

---

## Printing

The "Print" button prints **the sheet only** — the application UI is hidden
entirely. The sheet is typeset for white paper, paginates across as many pages
as it needs, prints every tab one after another, and tries to keep sections and
columns from splitting across a page break.

---

## Where this lives in the code

| What                              | Where                                                        |
| --------------------------------- | ------------------------------------------------------------ |
| Template schemas, reference checks | `backend/src/loregraph/schemas/entity_template.py`           |
| Formula grammar (parsing)          | `backend/src/loregraph/schemas/formula.py`                   |
| Formula evaluation                 | `frontend/src/components/sheet/widgets/formula.ts`           |
| Built-in templates and presets     | `backend/src/loregraph/templates/`                           |
| Sheet renderer (4 modes)           | `frontend/src/components/sheet/SheetRenderer.tsx`            |
| Designer                           | `frontend/src/components/sheet/designer/`                    |

The grammar is implemented twice — parsing on the backend (validation at
template-save time, where no field values exist yet) and parsing plus evaluation
on the frontend (where the entity's values do exist). The two are kept in
lockstep by a shared example table in `backend/tests/test_formula.py`: any change
to the grammar has to land in both files.
