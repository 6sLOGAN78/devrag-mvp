import type { TFunction } from "i18next";
import { ApiError } from "@/services/http";

const MAX_SERVER_MESSAGE = 160;

/** Retry-After is clamped to this range (seconds); the code itself lives 10 minutes. */
export const RETRY_AFTER_MIN = 1;
export const RETRY_AFTER_MAX = 600;

export function clampRetryAfter(seconds: number): number {
  return Math.min(RETRY_AFTER_MAX, Math.max(RETRY_AFTER_MIN, Math.floor(seconds)));
}

/** True for the server's refusal of a code or a ticket (HTTP 400): the only failures that are the user's input. */
export function isRefusal(error: unknown): boolean {
  return error instanceof ApiError && error.status === 400;
}

// The ticket refusal reads "This reset session is invalid or has expired...". A password rule reads "new password must
// be 8 to 128 characters". Both are HTTP 400, but only the first means the single-use ticket is gone (IN-F06).
const TICKET_WORDS = /\b(session|ticket|expired)\b/i;

/** True for a 400 that rejected the new password itself: the ticket is still valid, so the user stays on step 3. */
export function isPasswordRejection(error: unknown): boolean {
  return isRefusal(error) && /\bpassword\b/i.test((error as ApiError).message) && !TICKET_WORDS.test((error as ApiError).message);
}

/** A short non-empty server message, or the fallback. Rendered as text only (T-02-86). */
export function serverMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  const message = error.message;
  return message.trim().length > 0 && message.length <= MAX_SERVER_MESSAGE ? message : fallback;
}

/**
 * The text for a failed request. Throttles and outages use fixed generic copy and a refusal (HTTP 400) shows the
 * server's own words, so nothing here depends on whether the account exists.
 */
export function resetErrorMessage(error: unknown, t: TFunction, refusalFallback: string): string {
  if (!(error instanceof ApiError)) return t("auth.error.fallback");
  if (error.status === 429) return t("auth.error.rateLimited");
  if (error.status === 503) return t("auth.error.unavailable");
  if (isRefusal(error)) return serverMessage(error, refusalFallback);
  return t("auth.error.fallback");
}
