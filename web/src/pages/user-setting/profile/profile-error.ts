import type { TFunction } from "i18next";
import { ApiError } from "@/services/http";

const MAX_SERVER_MESSAGE = 160;

/**
 * The text for a failed profile or password request. A throttle and an outage get fixed, translated sentences; a
 * rejection shows the server's own words when they are a short non-empty string (the Go endpoints return plain
 * validation messages and never echo input), otherwise the generic sentence.
 */
export function profileErrorMessage(error: unknown, t: TFunction): string {
  if (!(error instanceof ApiError)) return t("auth.error.fallback");
  if (error.status === 429) return t("auth.error.rateLimited");
  if (error.status === 503) return t("auth.error.unavailable");
  // Nginx and the Go body cap answer 413 (R-130); the proxy's own wording is not user copy.
  if (error.status === 413) return t("auth.error.tooLarge");
  if (error.status === 0 || error.status >= 500) return t("auth.error.fallback");
  const message = error.message;
  return message.trim().length > 0 && message.length <= MAX_SERVER_MESSAGE ? message : t("auth.error.fallback");
}
