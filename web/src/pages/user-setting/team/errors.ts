import type { TFunction } from "i18next";
import i18n from "@/i18n";
import { ApiError } from "@/services/http";
import { notifyError } from "@/services/notify";

/** Which action failed; picks the toast title. */
export type TeamAction = "respond" | "role" | "remove" | "withdraw" | "leave";

const MAX_SERVER_MESSAGE = 160;

function statusOf(error: unknown): number {
  return error instanceof ApiError ? error.status : 0;
}

/** True when the server says the thing is gone (404): the caller refreshes and tells the user, nothing else. */
export function isGone(error: unknown): boolean {
  return statusOf(error) === 404;
}

/**
 * Toast for a failed team action. Each cause has a fixed, translated message: the server text is never shown
 * here (the invite form is the one place that shows it). The caller refetches, so the list never keeps stale state.
 */
export function notifyTeamFailure(error: unknown, action: TeamAction): void {
  const status = statusOf(error);
  let description = i18n.t("team.error.generic");
  if (status === 404) description = i18n.t("team.error.gone");
  else if (status === 403) description = i18n.t("team.error.forbidden");
  else if (status === 429) description = i18n.t("team.error.rateLimited");
  notifyError({ id: `team:${action}:${status}`, title: i18n.t(`team.failed.${action}`), description });
}

/**
 * Message for a failed invitation. The server's answer for a missing account, an existing member, a pending
 * invitation or yourself (400, 404, 409) is shown exactly as returned and never extended with a hint of our own.
 */
export function inviteErrorMessage(error: unknown, t: TFunction): string {
  const status = statusOf(error);
  if (status === 429) {
    const seconds = error instanceof ApiError ? error.retryAfter : undefined;
    return seconds === undefined ? t("team.invite.error.rateLimited") : t("team.invite.error.rateLimitedIn", { seconds });
  }
  if (status === 403) return t("team.invite.error.forbidden");
  if (status === 400 || status === 404 || status === 409) {
    const message = error instanceof ApiError ? error.message.trim() : "";
    if (message !== "" && message.length <= MAX_SERVER_MESSAGE) return message;
  }
  return t("team.invite.error.fallback");
}
