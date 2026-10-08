/** The only module that reads or writes the access token in storage (T-10-01). */
const STORAGE_KEY = "Authorization";

type Listener = () => void;
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of [...listeners]) listener();
}

/**
 * Set only when the browser refused to store the token (blocked site data, quota, policy): the session then lives in
 * this variable for the lifetime of the tab. When storage works it is always null and storage is the single truth.
 */
let memoryToken: string | null = null;

/** The token as this tab last saw it, so a storage event can tell another tab's change from a no-op. */
let lastSeen: string | null = null;

export function getAuthorization(): string | null {
  if (memoryToken !== null) return memoryToken;
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value && value.length > 0 ? value : null;
  } catch {
    // Storage blocked: behave as signed out rather than crash the render tree (WR-F01).
    return null;
  }
}

export function setAuthorization(token: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, token);
    memoryToken = null;
  } catch {
    memoryToken = token;
  }
  lastSeen = getAuthorization();
  notify();
}

export function removeAuthorization(): void {
  memoryToken = null;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage blocked: nothing persisted, nothing to remove */
  }
  lastSeen = getAuthorization();
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

/**
 * Calls `handler(current, previous)` when another tab removes or replaces the stored token (a storage event whose
 * outcome differs from what this tab last saw). Changes made here never fire it, nor does an event that changed
 * nothing, so one foreign change is reported exactly once. Returns the unsubscribe function (WR-F02).
 */
export function onForeignTokenChange(handler: (current: string | null, previous: string | null) => void): () => void {
  lastSeen = getAuthorization();
  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY && event.key !== null) return;
    const current = getAuthorization();
    if (current === lastSeen) return;
    const previous = lastSeen;
    lastSeen = current;
    handler(current, previous);
  };
  window.addEventListener("storage", onStorage);
  return () => window.removeEventListener("storage", onStorage);
}
