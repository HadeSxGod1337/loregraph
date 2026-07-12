import type { TFunction } from "i18next";

import type { AgentWarning } from "../api/agent";
import { ApiError } from "../api/client";

/** Renders one AgentWarning. `llm_text` is free text from an LLM judge,
 * already in the conversation's language — shown as-is, not looked up in
 * the catalog. Everything else is a `warnings.<code>` key with `params`
 * interpolated; an unrecognized code still shows something (the code
 * itself) instead of silently vanishing. */
export function translateWarning(warning: AgentWarning, t: TFunction): string {
  if (warning.code === "llm_text") {
    return warning.params.text ?? "";
  }
  return t(`warnings.${warning.code}`, { ...warning.params, defaultValue: warning.code });
}

/** Renders a deterministic, backend-composed chat event (see
 * agent/events.py). `draft_failed` is special-cased: its `reason_codes`
 * param is a comma-separated list of warning codes explaining *why*, so the
 * rendered sentence lists each translated reason instead of just the
 * generic "couldn't produce a draft". */
export function translateEvent(
  code: string,
  params: Record<string, string>,
  fallbackText: string,
  t: TFunction,
): string {
  if (code === "draft_failed") {
    const reasons = (params.reason_codes ?? "")
      .split(",")
      .filter(Boolean)
      .map((reasonCode) => translateWarning({ code: reasonCode, params: {} }, t));
    const intro = t("events.draft_failed", { defaultValue: fallbackText });
    return reasons.length > 0 ? `${intro} ${reasons.join("; ")}` : intro;
  }
  return t(`events.${code}`, { ...params, defaultValue: fallbackText });
}

/** Renders an API error for display. Prefers the `errors.<code>` catalog
 * entry when the backend supplied a recognized code (see
 * loregraph.exceptions.error_code); falls back to the raw diagnostic
 * message otherwise — never shows nothing. */
export function translateApiError(err: unknown, t: TFunction): string {
  if (err instanceof ApiError && err.code) {
    return t(`errors.${err.code}`, { defaultValue: err.message });
  }
  return err instanceof Error ? err.message : String(err);
}
