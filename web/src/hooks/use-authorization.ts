import { useSyncExternalStore } from "react";
import { getAuthorization, subscribeAuthorization } from "@/utils/authorization";

/** The stored token, re-read whenever it is set, removed here, or changed in another tab. */
export function useAuthorization(): string | null {
  return useSyncExternalStore(subscribeAuthorization, getAuthorization, () => null);
}
