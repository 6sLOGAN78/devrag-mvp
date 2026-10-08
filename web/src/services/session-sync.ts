import { dropSessionState } from "@/services/http";
import { onForeignTokenChange } from "@/utils/authorization";

/**
 * Keeps this tab consistent with token changes made in another tab (WR-F02). When another tab signs out, signs in as
 * somebody else or clears site data, the previous identity must not stay on screen or in memory while requests carry a
 * different token: the user store and the whole query cache are dropped here. A removed token sends the auth guard to
 * /login; a replaced token makes session recovery fetch the new user. Nothing is toasted, because the user acted in
 * the other tab. Returns the function that removes the listener.
 */
export function installSessionSync(): () => void {
  return onForeignTokenChange(() => dropSessionState());
}
