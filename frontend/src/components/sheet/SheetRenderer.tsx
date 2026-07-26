import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type {
  Entity,
  EntityField,
  FieldValue,
  SheetBlock,
  SheetContainer,
  SheetLayout,
  SheetRegion,
  SheetSection,
  TemplateFieldDef,
} from "../../api/types";
import { allBlocks } from "./designer/layoutOps";
import { parseDependencies } from "./widgets/formula";
import { defaultWidgetForFieldType } from "./widgets/registry";
import { WidgetView } from "./widgets/WidgetView";

type SheetMode = "compact" | "full" | "print" | "fill";

interface SheetRendererProps {
  entity: Entity;
  layout: SheetLayout;
  /** The template's own field defs — the only source of human labels
   * (EntityField carries none, only `key`); also lets the "other fields"
   * fallback show a real label instead of the raw key. */
  fieldDefs: TemplateFieldDef[];
  mode: SheetMode;
  /** Only meaningful in `fill` mode — renders real inputs bound to field
   * values instead of read-only text. The layout itself is NEVER mutated
   * from here regardless of mode: there is no drag-and-drop or layoutOps
   * call anywhere in this component tree, by construction, not by a UI
   * lock — "заполнять можно, раскладку менять нельзя" from the design. */
  onFieldChange?: (key: string, value: FieldValue) => void;
}

/** Renders an entity through a template's sheet layout, built from a flat
 * list of user-ordered Regions (band | columns | tabs — see api/types.ts).
 * One layout drives four surfaces via `mode`: `compact` (drawer — single
 * column, everything stacked), `full` (modal — columns side by side, tabs
 * switchable), `print` (like full, but every tab stacked instead of
 * switchable) and `fill` (the entity editor — like full, but editable). */
export function SheetRenderer({
  entity,
  layout,
  fieldDefs,
  mode,
  onFieldChange,
}: SheetRendererProps) {
  const { t } = useTranslation();
  const byKey = useMemo(() => {
    const map = new Map<string, EntityField>();
    for (const field of entity.fields) map.set(field.key, field);
    return map;
  }, [entity.fields]);
  const fieldValues = useMemo(() => {
    const values: Record<string, FieldValue> = {};
    for (const field of entity.fields) values[field.key] = field.value;
    return values;
  }, [entity.fields]);
  const fieldLabels = useMemo(() => {
    const map = new Map<string, string>();
    for (const def of fieldDefs) if (def.label) map.set(def.key, def.label);
    return map;
  }, [fieldDefs]);

  // "Other fields" exists so a layout can never hide data — but a field is
  // only genuinely unused if nothing references it: not a block's field_key,
  // not a computed formula's dependency, and not a tracker's max_field.
  // Without the last two, every proficiency boolean behind a skill formula
  // got dumped here as a raw true/false list.
  const extras = useMemo(() => {
    const used = new Set<string>();
    for (const block of allBlocks(layout)) {
      if (block.field_key) used.add(block.field_key);
      if (typeof block.config.max_field === "string") {
        used.add(block.config.max_field);
      }
      if (block.formula) {
        try {
          for (const dep of parseDependencies(block.formula)) used.add(dep);
        } catch {
          // Half-typed formula in the designer preview — ignore, the
          // inspector is where a broken formula gets reported.
        }
      }
    }
    return entity.fields.filter((f) => !used.has(f.key));
  }, [entity.fields, layout]);

  const regions = layout.regions;
  const headerRegion = regions[0]?.kind === "band" ? regions[0] : null;
  const bodyRegions = headerRegion ? regions.slice(1) : regions;
  const sectionProps = { byKey, fieldValues, fieldLabels, entityId: entity.id, onFieldChange };

  return (
    <div className={`sheet sheet-${mode}`}>
      <HeaderBand
        entity={entity}
        blocks={headerRegion?.blocks ?? []}
        {...sectionProps}
      />

      <div className="sheet-body">
        {bodyRegions.map((region, i) => (
          <RegionView key={region.id ?? i} region={region} mode={mode} {...sectionProps} />
        ))}

        {extras.length > 0 && (
          <SectionView
            section={{
              title: t("sheet.otherFields"),
              columns: 1,
              blocks: extras.map((f) => ({
                widget: defaultWidgetForFieldType(f.field_type),
                field_key: f.key,
                formula: null,
                label: fieldLabels.get(f.key) ?? f.key,
                colspan: 1,
                config: {},
              })),
            }}
            compact
            {...sectionProps}
          />
        )}
      </div>
    </div>
  );
}

interface WidgetPassthrough {
  byKey: Map<string, EntityField>;
  fieldValues: Record<string, FieldValue>;
  fieldLabels: Map<string, string>;
  entityId: string;
  onFieldChange?: (key: string, value: FieldValue) => void;
}

function HeaderBand({
  entity,
  blocks,
  ...pass
}: WidgetPassthrough & { entity: Entity; blocks: SheetBlock[] }) {
  const portrait = blocks.find((b) => b.widget === "image");
  const stats = blocks.filter((b) => b.widget !== "image");
  return (
    <div className="sheet-headerband">
      {portrait && (
        <div className="sheet-hb-portrait">
          <WidgetView block={portrait} {...pass} />
        </div>
      )}
      <div className="sheet-hb-identity">
        <div className="sheet-hb-name">{entity.title}</div>
        <div className="sheet-hb-type">{entity.type}</div>
      </div>
      {stats.length > 0 && (
        <div className="sheet-hb-stats">
          {stats.map((block, i) => (
            <div className="sheet-hb-pill" key={block.id ?? i}>
              <WidgetView block={block} {...pass} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RegionView({
  region,
  mode,
  ...sectionProps
}: WidgetPassthrough & { region: SheetRegion; mode: SheetMode }) {
  const compact = mode === "compact";
  // Declared unconditionally (Rules of Hooks) even though only the "tabs"
  // branch below reads it — the designer's live preview can flip a region's
  // `kind` while this component stays mounted under the same key.
  const [activeIndex, setActiveIndex] = useState(0);

  if (region.kind === "band") {
    return (
      <div className="sheet-band-row">
        {region.name && <h4 className="sheet-region-title">{region.name}</h4>}
        <div className="sheet-band-fields">
          {region.blocks.map((block, i) => (
            <div className="sheet-band-field" key={block.id ?? i}>
              <WidgetView block={block} {...sectionProps} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // columns: side by side in full/fill/print, stacked in compact.
  // tabs: a switchable tab bar in full/fill, every container stacked
  // (with its title as a heading) in compact/print — paper/narrow-drawer
  // have no room for interactive switching.
  const showTabBar = region.kind === "tabs" && (mode === "full" || mode === "fill");
  // Carries each container's index in the region, not its position in the
  // rendered slice: with a tab bar the slice is always length 1, so keying by
  // that index made every tab the same React key. The subtree was then reused
  // across tab switches, and stateful children (rich-text editors) kept the
  // previous tab's document.
  const shownContainers: { container: SheetContainer; index: number }[] = showTabBar
    ? region.containers
        .map((container, index) => ({ container, index }))
        .filter(({ index }) => index === activeIndex)
    : region.containers.map((container, index) => ({ container, index }));

  return (
    <div className={region.kind === "columns" ? "sheet-region-columns" : "sheet-region-tabs"}>
      {region.name && !showTabBar && (
        <h4 className="sheet-region-title">{region.name}</h4>
      )}
      {showTabBar && (
        <div className="sheet-tabbar" role="tablist">
          {region.containers.map((container, i) => (
            <button
              key={container.id ?? i}
              type="button"
              role="tab"
              aria-selected={i === activeIndex}
              className={i === activeIndex ? "sheet-tab active" : "sheet-tab"}
              onClick={() => setActiveIndex(i)}
            >
              {container.title ?? region.name}
            </button>
          ))}
        </div>
      )}
      {/* Column count is decided by available width (CSS auto-fit), not by
          `mode` — the same sheet renders in a wide modal, a narrow drawer
          and the designer's preview pane, and only the container knows how
          much room there actually is. */}
      <div className="sheet-columns">
        {shownContainers.map(({ container, index }) => (
          <div className="sheet-column" key={container.id ?? index}>
            {!showTabBar && container.title && region.containers.length > 1 && (
              <h5 className="sheet-container-title">{container.title}</h5>
            )}
            {container.sections.map((section, si) => (
              <SectionView
                key={section.id ?? `${index}-${si}`}
                section={section}
                compact={compact}
                {...sectionProps}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function SectionView({
  section,
  compact,
  ...pass
}: WidgetPassthrough & { section: SheetSection; compact: boolean }) {
  // stat_modifier/dots are small square boxes that pack into a dense
  // auto-fill grid; computed rows are full-width label+checkbox+value rows
  // (see .sheet-computed-row) and must NOT be squeezed into that grid — a
  // section of pure computed skills stays a normal single/multi-column list.
  const isStats =
    section.blocks.length > 0 &&
    section.blocks.every((b) => b.widget === "stat_modifier" || b.widget === "dots");
  // Stats sections auto-fill a dense box grid. Others treat `columns` as a
  // maximum, not a promise: auto-fit drops to fewer columns when the section
  // is narrow, so a 2-column section never overflows a drawer or preview.
  // minmax(0, …) everywhere: a bare `1fr` track has an `auto` minimum, so it
  // refuses to shrink below its content and pushes a horizontal scrollbar
  // into narrow panes. `min(170px, 100%)` keeps the same guarantee for the
  // multi-column case when the section itself is under 170px.
  const template = isStats
    ? null
    : compact || section.columns <= 1
      ? "minmax(0, 1fr)"
      : "repeat(auto-fit, minmax(min(170px, 100%), 1fr))";
  return (
    <section className={isStats ? "sheet-section sheet-section-stats" : "sheet-section"}>
      {section.title && <h4 className="sheet-section-title">{section.title}</h4>}
      <div
        className="sheet-grid"
        style={template ? { gridTemplateColumns: template } : undefined}
      >
        {section.blocks.map((block, i) => {
          const span = Math.max(1, block.colspan);
          return (
            <div
              key={block.id ?? i}
              className={`sheet-block sheet-block-${block.widget}`}
              style={span > 1 ? { gridColumn: `span ${span}` } : undefined}
            >
              <WidgetView block={block} {...pass} />
            </div>
          );
        })}
      </div>
    </section>
  );
}
