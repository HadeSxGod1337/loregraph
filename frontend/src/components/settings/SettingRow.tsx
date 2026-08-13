import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { SECRET_MASK_PREFIX, type SettingField } from "../../api/appSettings";
import { Checkbox } from "../ui/Checkbox";

interface Option {
  value: string;
  label: string;
}

interface Props {
  /** Server-side description of this field: its source, whether it is a
   * secret, whether a change needs a restart. Undefined while loading. */
  field: SettingField | undefined;
  label: string;
  hint?: string;
  value: unknown;
  options?: Option[];
  /** Datalist entries — the input stays free text either way, because a
   * provider's model list is never guaranteed complete. */
  suggestions?: string[];
  placeholder?: string;
  linkUrl?: string | null;
  linkLabel?: string;
  onChange: (value: unknown) => void;
  onReset: (name: string) => void;
}

/** One configurable setting, rendered from its type and its source.
 *
 * The source badge is the answer to "I edited .env and nothing happened":
 * a value set here overrides the file, and the badge says so, with a reset
 * that hands the field back to .env. */
export function SettingRow({
  field,
  label,
  hint,
  value,
  options,
  suggestions,
  placeholder,
  linkUrl,
  linkLabel,
  onChange,
  onReset,
}: Props) {
  const { t } = useTranslation();
  const inputId = useId();
  const listId = useId();
  // A stored key is only ever shown as a mask; replacing it is a deliberate
  // step, so a stray keystroke can't wipe a working key.
  const [replacing, setReplacing] = useState(false);
  // Raw text of a numeric field while it is being edited (null = show the
  // committed value).
  const [numberText, setNumberText] = useState<string | null>(null);

  if (field === undefined) return null;

  const showingMask =
    field.secret && field.is_set && !replacing && typeof value === "string" &&
    value.startsWith(SECRET_MASK_PREFIX);

  return (
    <div className="setting-row">
      <div className="setting-row-head">
        <label htmlFor={inputId}>{label}</label>
        <SourceBadge field={field} onReset={() => onReset(field.name)} />
      </div>

      {options !== undefined ? (
        <select
          id={inputId}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : typeof value === "boolean" ? (
        // The row head already carries the field name; the checkbox's own
        // label says what turning it on does, so the two don't repeat.
        <Checkbox
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
          label={hint ?? label}
        />
      ) : typeof value === "number" ? (
        <input
          id={inputId}
          type="number"
          value={numberText ?? String(value)}
          onChange={(e) => {
            // The field is briefly empty while retyping; committing 0 for
            // that would silently set a token budget of zero, so the empty
            // string lives here and only a parsed number is committed.
            setNumberText(e.target.value);
            if (e.target.value !== "") onChange(Number(e.target.value));
          }}
          onBlur={() => setNumberText(null)}
        />
      ) : showingMask ? (
        <div className="setting-secret-row">
          <input id={inputId} value={String(value)} readOnly />
          <button
            type="button"
            onClick={() => {
              setReplacing(true);
              // Start from empty, not from the mask — otherwise the first
              // keystroke would append to "••••1234" and save that.
              onChange("");
            }}
          >
            {t("appSettings.replaceKey")}
          </button>
          <button type="button" onClick={() => onChange("")}>
            {t("appSettings.clearKey")}
          </button>
        </div>
      ) : (
        <input
          id={inputId}
          type={field.secret ? "password" : "text"}
          value={typeof value === "string" ? value : ""}
          placeholder={placeholder}
          list={suggestions?.length ? listId : undefined}
          autoComplete={field.secret ? "off" : undefined}
          onChange={(e) => onChange(e.target.value)}
        />
      )}

      {suggestions !== undefined && suggestions.length > 0 && (
        <datalist id={listId}>
          {suggestions.map((suggestion) => (
            <option key={suggestion} value={suggestion} />
          ))}
        </datalist>
      )}

      {hint !== undefined && typeof value !== "boolean" && (
        <p className="field-hint">{hint}</p>
      )}

      {linkUrl != null && (
        <a className="field-hint" href={linkUrl} target="_blank" rel="noreferrer">
          {linkLabel ?? linkUrl}
        </a>
      )}

      {field.restart_required && (
        <p className="field-hint warning-hint">{t("appSettings.restartRequiredHint")}</p>
      )}
    </div>
  );
}

function SourceBadge({ field, onReset }: { field: SettingField; onReset: () => void }) {
  const { t } = useTranslation();
  if (field.source === "db") {
    return (
      <span className="setting-source">
        <span className="setting-source-badge db">{t("appSettings.sourceDb")}</span>
        <button type="button" className="link-button" onClick={onReset}>
          {t("appSettings.resetToEnv")}
        </button>
      </span>
    );
  }
  if (field.source === "env") {
    return (
      <span className="setting-source">
        <span className="setting-source-badge env" title={t("appSettings.sourceEnvHint")}>
          {t("appSettings.sourceEnv")}
        </span>
      </span>
    );
  }
  return null;
}
