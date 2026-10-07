import { useMemo } from "react";
import * as authService from "@/services/auth-service";
import { purgeSession } from "@/services/http";

/**
 * The three forgot-password requests as plain async calls, not TanStack mutations: a mutation would keep its
 * variables, and so the code, the reset ticket and the new password, in the mutation cache (T-02-85). All of them are
 * silent and anonymous (see auth-service); the page shows every message itself.
 */
export function usePasswordResetRequest() {
  return useMemo(
    () => ({
      requestCode: authService.requestResetCode,
      verifyCode: authService.verifyResetCode,
      /** Sets the password, then ends any session this browser held (D-08): the server has already signed every device out. */
      async resetPassword(email: string, ticket: string, newPassword: string): Promise<void> {
        await authService.resetPassword(email, ticket, newPassword);
        purgeSession({ toast: false, navigate: false });
      },
    }),
    [],
  );
}
