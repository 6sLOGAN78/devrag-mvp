import i18n from "@/i18n";
import { ApiError } from "@/services/http";
import { notifyError } from "@/services/notify";

/** The per-workspace cap on tokens (R-121); only used to word the message, the server enforces it. */
export const MAX_TOKENS = 50;

/**
 * Shows the toast for a failed create. Each cause has its own fixed, translated message; the server text and any
 * status detail are never shown, and no token is involved.
 */
export function notifyCreateFailure(error: unknown): void {
  const status = error instanceof ApiError ? error.status : 0;
  if (status === 409) {
    notifyError({ id: "tokens:create:limit", title: i18n.t("tokens.error.limit.title"), description: i18n.t("tokens.error.limit.body", { max: MAX_TOKENS }) });
  } else if (status === 429) {
    notifyError({ id: "tokens:create:rate", title: i18n.t("tokens.error.rateLimited.title"), description: i18n.t("tokens.error.rateLimited.body") });
  } else if (status === 403) {
    notifyError({ id: "tokens:create:forbidden", title: i18n.t("tokens.error.create.title"), description: i18n.t("tokens.error.ownerOnly") });
  } else {
    notifyError({ id: "tokens:create:failed", title: i18n.t("tokens.error.create.title"), description: i18n.t("tokens.error.create.body") });
  }
}

/** True when a delete failed because the token no longer exists (another tab, or already deleted): refresh, do not alarm. */
export function isAlreadyGone(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export function notifyDeleteFailure(): void {
  notifyError({ id: "tokens:delete:failed", title: i18n.t("tokens.error.delete.title"), description: i18n.t("tokens.error.delete.body") });
}
