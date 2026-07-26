import type { FieldType, WidgetType } from "../../../api/types";

export interface WidgetMeta {
  /** i18n key for the designer's widget picker. */
  labelKey: string;
  /** Stored field types this widget can render. Empty for decorative widgets
   * and for formula-bound ones (see formulaBound). */
  accepts: FieldType[];
  /** Decorative widgets (heading/divider) bind no field. */
  decorative: boolean;
  /** Formula-bound widgets (computed) bind no single field_key — their value
   * comes from Block.formula over the template's field_defs instead. Never
   * true at the same time as decorative. */
  formulaBound?: boolean;
}

/** The single place that knows every widget. Adding a widget = one entry here
 * (+ a case in WidgetView). Both the renderer and the designer read this, so
 * the field-type ↔ widget compatibility never diverges from the backend. */
export const WIDGET_META: Record<WidgetType, WidgetMeta> = {
  plain: {
    labelKey: "widgets.plain",
    accepts: ["text", "number", "boolean"],
    decorative: false,
  },
  rich_text: { labelKey: "widgets.rich_text", accepts: ["rich_text"], decorative: false },
  tag_chips: { labelKey: "widgets.tag_chips", accepts: ["tag"], decorative: false },
  image: { labelKey: "widgets.image", accepts: ["attachment", "text"], decorative: false },
  heading: { labelKey: "widgets.heading", accepts: [], decorative: true },
  divider: { labelKey: "widgets.divider", accepts: [], decorative: true },
  stat_modifier: {
    labelKey: "widgets.stat_modifier",
    accepts: ["number"],
    decorative: false,
  },
  dots: { labelKey: "widgets.dots", accepts: ["number"], decorative: false },
  tracker: { labelKey: "widgets.tracker", accepts: ["number"], decorative: false },
  computed: {
    labelKey: "widgets.computed",
    accepts: [],
    decorative: false,
    formulaBound: true,
  },
};

export const WIDGET_TYPES = Object.keys(WIDGET_META) as WidgetType[];

/** Widgets that can render a field of this stored type (decorative excluded). */
export function widgetsForFieldType(fieldType: FieldType): WidgetType[] {
  return WIDGET_TYPES.filter(
    (w) => !WIDGET_META[w].decorative && WIDGET_META[w].accepts.includes(fieldType),
  );
}

/** Sensible default widget when a field is dropped onto the sheet. */
export function defaultWidgetForFieldType(fieldType: FieldType): WidgetType {
  switch (fieldType) {
    case "rich_text":
      return "rich_text";
    case "tag":
      return "tag_chips";
    case "attachment":
      return "image";
    default:
      return "plain";
  }
}
