import { useMemo } from "react";
import * as authService from "@/services/auth-service";
import { purgeSession } from "@/services/http";
import { useUserStore } from "@/stores/user-store";

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
      /**
       * Sets the password, then ends this browser's session when it belongs to the reset account (D-08): the server has
       * already signed that account out everywhere. A session known to belong to a different account is left alone.
       */
      async resetPassword(email: string, ticket: string, newPassword: string): Promise<void> {
        await authService.resetPassword(email, ticket, newPassword);
        const signedInAs = useUserStore.getState().user?.email;
        if (signedInAs === undefined || signedInAs.trim().toLowerCase() === email.trim().toLowerCase()) {
          purgeSession({ toast: false, navigate: false });
        }
      },
    }),
    [],
  );
}
