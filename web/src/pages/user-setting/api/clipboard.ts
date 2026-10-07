import i18n from "@/i18n";
import { notifyError, notifySuccess } from "@/services/notify";

/**
 * Writes text with the async Clipboard API. Resolves false when the API is missing (insecure context, old browser)
 * or the write is rejected (permission, focus). There is deliberately no `execCommand` fallback: it would need a
 * hidden element holding the token.
 */
export async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (typeof navigator === "undefined" || typeof navigator.clipboard?.writeText !== "function") return false;
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** Copies a token and tells the user how it went with fixed texts; the toast never contains the token. Returns success. */
export async function copyToken(token: string): Promise<boolean> {
  const copied = await writeClipboard(token);
  if (copied) {
    notifySuccess(i18n.t("tokens.copied"));
  } else {
    notifyError({ id: "tokens:copy-failed", title: i18n.t("tokens.copyFailed.title"), description: i18n.t("tokens.copyFailed.body") });
  }
  return copied;
}
