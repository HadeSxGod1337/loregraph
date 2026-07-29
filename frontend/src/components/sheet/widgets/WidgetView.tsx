import { API_URL } from "../../../api/client";
import type {
  AttachmentRef,
  EntityField,
  FieldType,
  FieldValue,
  ProseMirrorDoc,
  SheetBlock,
  TemplateFieldDef,
} from "../../../api/types";
import { RichTextField } from "../../entity/RichTextField";
import { RichTextView } from "../../entity/RichTextView";
import { emptyValue } from "../applyTemplate";
import { DEFAULT_STAT_MOD_FORMULA, evaluateFormula, STAT_VALUE_IDENT } from "./formula";

export interface WidgetContext {
  /** The entity's own fields, by key — absent when the entity never carried
   * that field (see `defsByKey`). */
  byKey: Map<string, EntityField>;
  fieldValues: Record<string, FieldValue>;
  /** The template's field defs by key — the only source of human labels
   * (EntityField carries none) and the type to create a field with when the
   * DM fills in a slot the entity does not have yet. */
  defsByKey: Map<string, TemplateFieldDef>;
  entityId?: string;
  onFieldChange?: (key: string, value: FieldValue, fieldType: FieldType) => void;
}

/** Renders one block against the entity's fields. Read-only by default; pass
 * `onFieldChange` (only in SheetRenderer's `fill` mode) to render real
 * inputs instead — the layout itself is never mutated either way, only field
 * values. The switch here pairs with WIDGET_META in registry.ts — add a
 * widget in both places. */
export function WidgetView({ block, ...ctx }: { block: SheetBlock } & WidgetContext) {
  const { byKey, defsByKey, fieldValues, entityId, onFieldChange } = ctx;

  if (block.widget === "heading") {
    return <h4 className="sheet-heading">{block.label ?? ""}</h4>;
  }
  if (block.widget === "divider") {
    return <hr className="sheet-divider" />;
  }
  if (block.widget === "computed") {
    return (
      <ComputedWidget
        block={block}
        byKey={byKey}
        defsByKey={defsByKey}
        fieldValues={fieldValues}
        onFieldChange={onFieldChange}
      />
    );
  }

  const def = block.field_key ? defsByKey.get(block.field_key) : undefined;
  const stored = block.field_key ? byKey.get(block.field_key) : undefined;
  // `??`, not `||`: an explicit empty label means "no caption on this block"
  // (the ability box inside a section already titled "Сила"), while `null`
  // means "fall back to whatever the field itself is called".
  const label = block.label ?? def?.label ?? stored?.key ?? block.field_key ?? "";

  // A block can point at a field the entity does not carry yet. While filling
  // in, that slot must still be editable — synthesise an empty field of the
  // template's declared type and let applyFieldValue append it on first edit.
  const field: EntityField | undefined =
    stored ??
    (onFieldChange && def
      ? {
          key: def.key,
          field_type: def.field_type,
          value: def.default_value ?? emptyValue(def.field_type),
          show_on_card: def.show_on_card,
        }
      : undefined);

  if (onFieldChange && field !== undefined) {
    return (
      <EditableWidget
        block={block}
        field={field}
        label={label}
        entityId={entityId}
        byKey={byKey}
        defsByKey={defsByKey}
        fieldValues={fieldValues}
        onFieldChange={onFieldChange}
      />
    );
  }

  if (field === undefined || field.value === "" || field.value === null) {
    // Field placed but empty — show the labelled slot (we render all fields).
    if (block.widget === "stat_modifier") {
      return <StatModifier value={0} label={label} empty />;
    }
    // An empty picture is nothing to frame — a labelled dashed slot where a
    // portrait belongs just clutters the header band.
    if (block.widget === "image") return null;
    return (
      <>
        <span className="sheet-label">{label}</span>
        <span className="sheet-value sheet-value-empty" />
      </>
    );
  }

  switch (block.widget) {
    case "rich_text":
      return (
        <>
          <span className="sheet-label">{label}</span>
          <div className="sheet-value sheet-value-rich">
            {/* Keyed by the field it shows: an editor is stateful, and if
                React ever reuses one instance for a different field (same
                position in a re-rendered tab), the key is what forces a fresh
                one instead of leaving the old document on screen. */}
            <RichTextView key={field.key} value={field.value as ProseMirrorDoc} />
          </div>
        </>
      );
    case "tag_chips":
      return (
        <>
          <span className="sheet-label">{label}</span>
          <div className="sheet-value sheet-chips">
            {(field.value as string[]).map((tag) => (
              <span className="sheet-chip" key={tag}>
                {tag}
              </span>
            ))}
          </div>
        </>
      );
    case "image":
      return <ImageWidget field={field} label={label} />;
    case "stat_modifier":
      return (
        <StatModifier
          value={Number(field.value)}
          label={label}
          modifier={statModifier(block, Number(field.value), fieldValues)}
        />
      );
    case "dots":
      return (
        <Dots
          value={Number(field.value)}
          max={Number(block.config.max ?? 5)}
          label={label}
        />
      );
    case "tracker":
      return (
        <Tracker value={Number(field.value)} max={trackerMax(block, byKey)} label={label} />
      );
    default:
      return (
        <>
          <span className="sheet-label">{label}</span>
          <span className="sheet-value">{formatValue(field.value)}</span>
        </>
      );
  }
}

/** Booleans read as ✓/— on a sheet; "true"/"false" is database output, not
 * something a DM should see on a character sheet. */
function formatValue(value: FieldValue): string {
  if (typeof value === "boolean") return value ? "✓" : "—";
  return String(value);
}

function ComputedWidget({
  block,
  byKey,
  defsByKey,
  fieldValues,
  onFieldChange,
}: { block: SheetBlock } & WidgetContext) {
  const label = block.label ?? "";
  let result: number | boolean = 0;
  try {
    result = block.formula ? evaluateFormula(block.formula, fieldValues) : 0;
  } catch {
    // Malformed formula (mid-edit in the designer) — show a neutral value
    // rather than crashing the sheet; the designer's inspector is where a
    // bad formula gets surfaced to the DM.
    result = 0;
  }
  // A leading "+" says "add this to a roll". Only a modifier means that: a
  // saving throw does, a passive score or a carrying capacity does not, and
  // "+13" for passive perception is simply wrong. Opt in per block.
  const signed = block.config.signed === true;
  const display =
    typeof result === "boolean"
      ? result
        ? "✓"
        : "—"
      : signed
        ? formatSigned(result)
        : String(round2(result));
  const toggleable = Array.isArray(block.config.toggleable)
    ? (block.config.toggleable as string[])
    : [];
  return (
    <div className="sheet-computed-row">
      {toggleable.map((key) => {
        const checked = Boolean(byKey.get(key)?.value ?? defsByKey.get(key)?.default_value);
        return (
          <input
            key={key}
            type="checkbox"
            className="sheet-computed-toggle"
            checked={checked}
            aria-label={defsByKey.get(key)?.label ?? key}
            disabled={!onFieldChange}
            onChange={
              onFieldChange
                ? (e) => onFieldChange(key, e.target.checked, "boolean")
                : undefined
            }
          />
        );
      })}
      <span className="sheet-label">{label}</span>
      <span className="sheet-value sheet-computed-value">{display}</span>
    </div>
  );
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function formatSigned(n: number): string {
  const rounded = round2(n);
  return rounded >= 0 ? `+${rounded}` : `${rounded}`;
}

/** How a stat_modifier's derived number is computed. Which arithmetic that is
 * belongs to the game system, not to the renderer — a block carries its own
 * `mod_formula` (over STAT_VALUE_IDENT plus the entity's other fields) and
 * only falls back to the D&D 5e rule when it declares nothing. `null` hides
 * the modifier line entirely, for systems that have no such concept. */
function statModifier(
  block: SheetBlock,
  value: number,
  fieldValues: Record<string, FieldValue>,
): number | null {
  const raw = block.config.mod_formula;
  if (raw === null) return null;
  const formula = typeof raw === "string" && raw.trim() ? raw : DEFAULT_STAT_MOD_FORMULA;
  try {
    const result = evaluateFormula(formula, {
      ...fieldValues,
      [STAT_VALUE_IDENT]: value,
    });
    return typeof result === "boolean" ? (result ? 1 : 0) : result;
  } catch {
    return null;
  }
}

function EditableWidget({
  block,
  field,
  label,
  entityId,
  byKey,
  defsByKey,
  fieldValues,
  onFieldChange,
}: {
  block: SheetBlock;
  field: EntityField;
  label: string;
  entityId: string | undefined;
  byKey: Map<string, EntityField>;
  defsByKey: Map<string, TemplateFieldDef>;
  fieldValues: Record<string, FieldValue>;
  onFieldChange: (key: string, value: FieldValue, fieldType: FieldType) => void;
}) {
  const set = (value: FieldValue) => onFieldChange(field.key, value, field.field_type);

  switch (block.widget) {
    case "plain":
      if (field.field_type === "boolean") {
        return (
          <label className="sheet-inline-checkbox">
            <input
              type="checkbox"
              checked={Boolean(field.value)}
              onChange={(e) => set(e.target.checked)}
            />
            <span className="sheet-label">{label}</span>
          </label>
        );
      }
      if (field.field_type === "number") {
        return (
          <>
            <span className="sheet-label">{label}</span>
            <input
              className="sheet-input"
              type="number"
              aria-label={label}
              value={field.value as number}
              onChange={(e) => set(Number(e.target.value))}
            />
          </>
        );
      }
      return (
        <>
          <span className="sheet-label">{label}</span>
          <input
            className="sheet-input"
            type="text"
            aria-label={label}
            value={field.value as string}
            onChange={(e) => set(e.target.value)}
          />
        </>
      );
    case "rich_text":
      return (
        <>
          <span className="sheet-label">{label}</span>
          <RichTextField
            key={field.key}
            value={field.value as ProseMirrorDoc}
            entityId={entityId}
            onChange={(doc) => set(doc)}
          />
        </>
      );
    case "tag_chips":
      return (
        <>
          <span className="sheet-label">{label}</span>
          <input
            className="sheet-input"
            type="text"
            aria-label={label}
            value={(field.value as string[]).join(", ")}
            onChange={(e) =>
              set(
                e.target.value
                  .split(",")
                  .map((v) => v.trim())
                  .filter((v) => v.length > 0),
              )
            }
          />
        </>
      );
    case "image":
      return (
        <div className="sheet-image-edit">
          <ImageWidget field={field} label={label} />
          {field.field_type === "text" && (
            <input
              className="sheet-input"
              type="text"
              aria-label={label}
              value={field.value as string}
              onChange={(e) => set(e.target.value)}
            />
          )}
        </div>
      );
    case "stat_modifier":
      return (
        <StatModifier
          value={Number(field.value)}
          label={label}
          modifier={statModifier(block, Number(field.value), fieldValues)}
          onChange={(v) => set(v)}
        />
      );
    case "dots":
      return (
        <Dots
          value={Number(field.value)}
          max={Number(block.config.max ?? 5)}
          label={label}
          onChange={(v) => set(v)}
        />
      );
    case "tracker": {
      // The max lives in its own field. It is excluded from "Прочие поля"
      // (SheetRenderer counts it as placed), so this widget is the only
      // place it can ever be edited — a tracker whose max is fixed forever
      // is not a tracker.
      const maxKey = typeof block.config.max_field === "string"
        ? block.config.max_field
        : null;
      const maxDef = maxKey ? defsByKey.get(maxKey) : undefined;
      return (
        <Tracker
          value={Number(field.value)}
          max={trackerMax(block, byKey)}
          label={label}
          onChange={(v) => set(v)}
          onMaxChange={
            maxKey
              ? (v) => onFieldChange(maxKey, v, maxDef?.field_type ?? "number")
              : undefined
          }
        />
      );
    }
    default:
      return (
        <>
          <span className="sheet-label">{label}</span>
          <span className="sheet-value">{formatValue(field.value)}</span>
        </>
      );
  }
}

function ImageWidget({ field, label }: { field: EntityField; label: string }) {
  const src =
    field.field_type === "attachment"
      ? // An attachment slot the entity never filled in has an empty url;
        // prefixing API_URL to it yields the API root, which renders as a
        // broken-image glyph rather than nothing.
        attachmentUrl(field.value as AttachmentRef)
      : imageUrlFromText(String(field.value));
  if (!src) return null;
  return <img className="sheet-portrait" src={src} alt={label} />;
}

function attachmentUrl(ref: AttachmentRef | null): string {
  return ref?.url ? API_URL + ref.url : "";
}

function imageUrlFromText(value: string): string {
  if (/^https?:\/\//.test(value)) return value;
  // A bare word with no path separator (e.g. stray placeholder text typed
  // into the field) is never a real upload path — treat it as empty rather
  // than building a URL that 404s as a broken-image glyph.
  if (!value.includes("/")) return "";
  return API_URL + value;
}

function StatModifier({
  value,
  label,
  modifier,
  empty,
  onChange,
}: {
  value: number;
  label: string;
  modifier?: number | null;
  empty?: boolean;
  onChange?: (value: number) => void;
}) {
  const shown = modifier ?? null;
  return (
    <div className={empty ? "sheet-stat sheet-stat-empty" : "sheet-stat"}>
      {label && <span className="sheet-stat-label">{label}</span>}
      {onChange ? (
        <input
          className="sheet-stat-score-input"
          type="number"
          aria-label={label}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      ) : (
        <span className="sheet-stat-score">{value}</span>
      )}
      {shown !== null && <span className="sheet-stat-mod">{formatSigned(shown)}</span>}
    </div>
  );
}

function Dots({
  value,
  max,
  label,
  onChange,
}: {
  value: number;
  max: number;
  label: string;
  onChange?: (value: number) => void;
}) {
  return (
    <div className="sheet-dots-row">
      <span className="sheet-label">{label}</span>
      {/* radiogroup, not a row of decorative spans: rating dots were
          click-only before — `role="button"` on a <span> with no tabIndex and
          no key handler is unreachable from the keyboard entirely. */}
      <span
        className="sheet-dots"
        role={onChange ? "radiogroup" : undefined}
        aria-label={onChange ? label : `${value}/${max}`}
      >
        {Array.from({ length: max }, (_, i) =>
          onChange ? (
            <button
              key={i}
              type="button"
              role="radio"
              aria-checked={i + 1 === value}
              aria-label={`${i + 1}`}
              className={i < value ? "sheet-dot filled" : "sheet-dot"}
              // Clicking the currently-last filled dot clears back to it —
              // the only way to set a rating to zero.
              onClick={() => onChange(i + 1 === value ? i : i + 1)}
            />
          ) : (
            <span key={i} className={i < value ? "sheet-dot filled" : "sheet-dot"} />
          ),
        )}
      </span>
    </div>
  );
}

function Tracker({
  value,
  max,
  label,
  onChange,
  onMaxChange,
}: {
  value: number;
  max: number | null;
  label: string;
  onChange?: (value: number) => void;
  onMaxChange?: (value: number) => void;
}) {
  return (
    <div className="sheet-tracker">
      <span className="sheet-label">{label}</span>
      {onChange ? (
        <span className="sheet-tracker-edit">
          <input
            className="sheet-tracker-input"
            type="number"
            aria-label={label}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
          />
          {onMaxChange ? (
            <>
              <span className="sheet-tracker-max"> / </span>
              <input
                className="sheet-tracker-input"
                type="number"
                aria-label={`${label} max`}
                value={max ?? 0}
                onChange={(e) => onMaxChange(Number(e.target.value))}
              />
            </>
          ) : (
            max !== null && <span className="sheet-tracker-max"> / {max}</span>
          )}
        </span>
      ) : (
        <span className="sheet-value">{max === null ? value : `${value} / ${max}`}</span>
      )}
    </div>
  );
}

function trackerMax(
  block: SheetBlock,
  byKey: Map<string, EntityField>,
): number | null {
  const maxKey = block.config.max_field;
  if (typeof maxKey !== "string") return null;
  const field = byKey.get(maxKey);
  return field ? Number(field.value) : null;
}
