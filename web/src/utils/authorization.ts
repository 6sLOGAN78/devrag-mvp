/** The only module that reads or writes the access token in storage (T-10-01). */
const STORAGE_KEY = "Authorization";

export function getAuthorization(): string | null {
  const value = localStorage.getItem(STORAGE_KEY);
  return value && value.length > 0 ? value : null;
}

export function setAuthorization(token: string): void {
  localStorage.setItem(STORAGE_KEY, token);
}

export function removeAuthorization(): void {
  localStorage.removeItem(STORAGE_KEY);
}
