/**
 * Marks a deliberate sign out so the auth guard sends the visitor to a bare /login instead of adding a `next`
 * parameter (which is for expired sessions). Held in memory only; it is never persisted and carries no data.
 */
let signingOut = false;

export function beginSignOut(): void {
  signingOut = true;
}

export function endSignOut(): void {
  signingOut = false;
}

export function isSigningOut(): boolean {
  return signingOut;
}
