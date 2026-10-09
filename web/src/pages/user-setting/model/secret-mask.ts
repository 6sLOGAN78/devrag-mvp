/**
 * The one masking rule for saved provider keys (D-07, UI-SPEC choice 24). The SPA never holds a saved key: the server
 * supplies only the last four characters, and this module is the only place that turns them into display text.
 *
 *   masked = eight bullets + the last 4 characters the server supplied
 *
 * There is no reveal and no copy. A missing or short tail gives the bullets alone, and no input ever yields more than
 * four visible characters, so a malformed value cannot leak more than a well formed one.
 */
export const SECRET_BULLETS = "•".repeat(8);
export const SECRET_TAIL_LENGTH = 4;

export function maskSecret(last4: string): string {
  if (typeof last4 !== "string" || last4.length < SECRET_TAIL_LENGTH) return SECRET_BULLETS;
  return `${SECRET_BULLETS}${last4.slice(-SECRET_TAIL_LENGTH)}`;
}
