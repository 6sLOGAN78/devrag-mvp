/** Where a signed-in user lands when no safe `next` target exists. */
export const HOME_PATH = "/home";
const LOGIN_PATH = "/login";
const MAX_NEXT_LENGTH = 512;
// A single leading slash, not followed by another slash or a backslash (both mean "another host" to browsers).
const INTERNAL_PATH = /^\/(?![/\\])/;
// Control characters (browsers strip tab and newline from URLs, turning "/\t/host" into "//host").
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

function isInternalPath(value: string): boolean {
  return value.length <= MAX_NEXT_LENGTH && INTERNAL_PATH.test(value) && !CONTROL_CHARS.test(value);
}

/** Only a same-origin internal path may be followed after sign in; anything else falls back to home. */
export function sanitiseNext(next: string | null | undefined): string {
  return typeof next === "string" && isInternalPath(next) ? next : HOME_PATH;
}

/** The sign-in URL for a guarded location: `/login?next=<path+search>`, or bare `/login` from a public auth page. */
export function loginRedirect(currentPath: string): string {
  if (!isInternalPath(currentPath)) return LOGIN_PATH;
  if (/^\/(login|forgot-password)(?:[/?#]|$)/.test(currentPath)) return LOGIN_PATH;
  return `${LOGIN_PATH}?next=${encodeURIComponent(currentPath)}`;
}
