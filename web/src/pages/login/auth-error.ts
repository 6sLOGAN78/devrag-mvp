import type { TFunction } from "i18next";
import { ApiError } from "@/services/http";

const MAX_SERVER_MESSAGE = 160;

/**
 * The text for a failed sign in or sign up.
 *
 * Sign in never shows the server's words: any rejection that is not a throttle or an outage reads the same
 * pinned sentence, so an unknown email and a wrong password are indistinguishable (D-04, T-02-54). Sign up shows
 * the server's message as returned when it is a short non-empty string, since the API documents duplicate-email
 * and validation errors (UI-SPEC checker flag 1).
 */
export function authErrorMessage(error: unknown, kind: "login" | "register", t: TFunction): string {
  if (!(error instanceof ApiError)) return t("auth.error.fallback");
  if (error.status === 429) return t("auth.error.rateLimited");
  if (error.status === 503) return t("auth.error.unavailable");
  if (error.status === 0 || error.status >= 500) return t("auth.error.fallback");
  if (kind === "login") return t("auth.login.failed");
  const message = error.message;
  return message.trim().length > 0 && message.length <= MAX_SERVER_MESSAGE ? message : t("auth.error.fallback");
}
