/** The only module that reads or writes the access token in storage (T-10-01). */
const STORAGE_KEY = "Authorization";

type Listener = () => void;
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of [...listeners]) listener();
}

export function getAuthorization(): string | null {
  const value = localStorage.getItem(STORAGE_KEY);
  return value && value.length > 0 ? value : null;
}

export function setAuthorization(token: string): void {
  localStorage.setItem(STORAGE_KEY, token);
  notify();
}

export function removeAuthorization(): void {
  localStorage.removeItem(STORAGE_KEY);
  notify();
}

/**
 * Subscribes to token changes made here or in another tab (storage event), so the auth guard re-evaluates
 * when the token disappears. Returns the unsubscribe function.
 */
export function subscribeAuthorization(listener: Listener): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY || event.key === null) listener();
  };
  listeners.add(listener);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}
