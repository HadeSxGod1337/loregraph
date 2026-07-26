import { API_URL } from "../../../api/client";
import type {
  AttachmentRef,
  EntityField,
  FieldValue,
  ProseMirrorDoc,
  SheetBlock,
} from "../../../api/types";
import { RichTextField } from "../../entity/RichTextField";
import { RichTextView } from "../../entity/RichTextView";
import { evaluateFormula } from "./formula";

/** Renders one block against the entity's fields. Read-only by default; pass
 * `onFieldChange` (only in SheetRenderer's `fill` mode) to render real
 * inputs instead — the layout itself is never mutated either way, only field
 * values. The switch here pairs with WIDGET_META in registry.ts — add a
 * widget in both places. */
export function WidgetView({
  block,
  byKey,
  fieldValues,
  fieldLabels,
  entityId,
  onFieldChange,
}: {
  block: SheetBlock;
  byKey: Map<string, EntityField>;
  fieldValues: Record<string, FieldValue>;
  /** field_key -> template field def's human label — EntityField itself
   * carries no label, only the template's field_defs do. */
  fieldLabels: Map<string, string>;
  entityId?: string;
  onFieldChange?: (key: string, value: FieldValue) => void;
}) {
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
        fieldValues={fieldValues}
        onFieldChange={onFieldChange}
      />
    );
  }

  const field = block.field_key ? byKey.get(block.field_key) : undefined;
  const fieldLabel = block.field_key ? fieldLabels.get(block.field_key) : undefined;
  // `??`, not `||`: an explicit empty label means "no caption on this block"
  // (the ability box inside a section already titled "Сила"), while `null`
  // means "fall back to whatever the field itself is called".
  const label = block.label ?? fieldLabel ?? field?.key ?? "";

  if (onFieldChange && field !== undefined) {
    return (
      <EditableWidget
        block={block}
        field={field}
        label={label}
        entityId={entityId}
        byKey={byKey}
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
      return <StatModifier value={Number(field.value)} label={label} />;
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
  fieldValues,
  onFieldChange,
}: {
  block: SheetBlock;
  byKey: Map<string, EntityField>;
  fieldValues: Record<string, FieldValue>;
  onFieldChange?: (key: string, value: FieldValue) => void;
}) {
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
  const display =
    typeof result === "boolean" ? (result ? "✓" : "—") : formatSigned(result);
  const toggleable = Array.isArray(block.config.toggleable)
    ? (block.config.toggleable as string[])
    : [];
  return (
    <div className="sheet-computed-row">
      {toggleable.map((key) => (
        <input
          key={key}
          type="checkbox"
          className="sheet-computed-toggle"
          checked={Boolean(byKey.get(key)?.value)}
          disabled={!onFieldChange}
          onChange={
            onFieldChange ? (e) => onFieldChange(key, e.target.checked) : undefined
          }
        />
      ))}
      <span className="sheet-label">{label}</span>
      <span className="sheet-value sheet-computed-value">{display}</span>
    </div>
  );
}

function formatSigned(n: number): string {
  const rounded = Math.round(n * 100) / 100;
  return rounded >= 0 ? `+${rounded}` : `${rounded}`;
}

function EditableWidget({
  block,
  field,
  label,
  entityId,
  byKey,
  onFieldChange,
}: {
  block: SheetBlock;
  field: EntityField;
  label: string;
  entityId: string | undefined;
  byKey: Map<string, EntityField>;
  onFieldChange: (key: string, value: FieldValue) => void;
}) {
  switch (block.widget) {
    case "plain":
      if (field.field_type === "boolean") {
        return (
          <label className="sheet-inline-checkbox">
            <input
              type="checkbox"
              checked={Boolean(field.value)}
              onChange={(e) => onFieldChange(field.key, e.target.checked)}
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
              value={field.value as number}
              onChange={(e) => onFieldChange(field.key, Number(e.target.value))}
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
            value={field.value as string}
            onChange={(e) => onFieldChange(field.key, e.target.value)}
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
            onChange={(doc) => onFieldChange(field.key, doc)}
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
            value={(field.value as string[]).join(", ")}
            onChange={(e) =>
              onFieldChange(
                field.key,
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
              value={field.value as string}
              onChange={(e) => onFieldChange(field.key, e.target.value)}
            />
          )}
        </div>
      );
    case "stat_modifier":
      return (
        <StatModifier
          value={Number(field.value)}
          label={label}
          onChange={(v) => onFieldChange(field.key, v)}
        />
      );
    case "dots":
      return (
        <Dots
          value={Number(field.value)}
          max={Number(block.config.max ?? 5)}
          label={label}
          onChange={(v) => onFieldChange(field.key, v)}
        />
      );
    case "tracker":
      return (
        <Tracker
          value={Number(field.value)}
          max={trackerMax(block, byKey)}
          label={label}
          onChange={(v) => onFieldChange(field.key, v)}
        />
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

function ImageWidget({ field, label }: { field: EntityField; label: string }) {
  const src =
    field.field_type === "attachment"
      ? API_URL + (field.value as AttachmentRef).url
      : imageUrlFromText(String(field.value));
  if (!src) return null;
  return <img className="sheet-portrait" src={src} alt={label} />;
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
  empty,
  onChange,
}: {
  value: number;
  label: string;
  empty?: boolean;
  onChange?: (value: number) => void;
}) {
  const modifier = Math.floor((value - 10) / 2);
  const sign = modifier >= 0 ? "+" : "";
  return (
    <div className={empty ? "sheet-stat sheet-stat-empty" : "sheet-stat"}>
      {label && <span className="sheet-stat-label">{label}</span>}
      {onChange ? (
        <input
          className="sheet-stat-score-input"
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      ) : (
        <span className="sheet-stat-score">{value}</span>
      )}
      <span className="sheet-stat-mod">
        {sign}
        {modifier}
      </span>
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
      <span className="sheet-dots" aria-label={`${value}/${max}`}>
        {Array.from({ length: max }, (_, i) => (
          <span
            key={i}
            className={i < value ? "sheet-dot filled" : "sheet-dot"}
            role={onChange ? "button" : undefined}
            onClick={onChange ? () => onChange(i + 1 === value ? i : i + 1) : undefined}
          />
        ))}
      </span>
    </div>
  );
}

function Tracker({
  value,
  max,
  label,
  onChange,
}: {
  value: number;
  max: number | null;
  label: string;
  onChange?: (value: number) => void;
}) {
  return (
    <div className="sheet-tracker">
      <span className="sheet-label">{label}</span>
      {onChange ? (
        <span className="sheet-tracker-edit">
          <input
            className="sheet-tracker-input"
            type="number"
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
          />
          {max !== null && <span className="sheet-tracker-max"> / {max}</span>}
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
