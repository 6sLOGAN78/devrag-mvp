/**
 * The one masking rule for API tokens (UI-35, UI checker flag 6). Everything that shows a token in its hidden form
 * (table cell, accessible names that carry the tail, the home page) goes through this module:
 *
 *   masked   = "ragflow-" (the literal 8 character prefix) + eight bullets + the last 4 characters
 *   revealed = the full value (the table adds `break-all`; it is never truncated)
 *   copied   = always the full value, masked or not
 *
 * A value shorter than 13 characters, or one that does not start with the prefix, is masked completely (all bullets,
 * the same width), so a malformed value can never leak more than a well formed one.
 */
export const MASK_PREFIX = "ragflow-";
export const MASK_BULLETS = "•".repeat(8);
export const MASK_TAIL_LENGTH = 4;

const BULLET = "•";
const MIN_MASKABLE = MASK_PREFIX.length + MASK_TAIL_LENGTH + 1;

function isMaskable(token: string): boolean {
  return token.length >= MIN_MASKABLE && token.startsWith(MASK_PREFIX);
}

/** The last four characters, used in accessible names and dialog copy. Never more than four. */
export function tokenTail(token: string): string {
  return isMaskable(token) ? token.slice(-MASK_TAIL_LENGTH) : BULLET.repeat(MASK_TAIL_LENGTH);
}

/** The hidden form of a token under the rule above. */
export function maskToken(token: string): string {
  if (!isMaskable(token)) return BULLET.repeat(MASK_PREFIX.length + MASK_BULLETS.length + MASK_TAIL_LENGTH);
  return `${MASK_PREFIX}${MASK_BULLETS}${tokenTail(token)}`;
}
