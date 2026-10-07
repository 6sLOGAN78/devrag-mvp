import { useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import * as authService from "@/services/auth-service";
import { getUserInfo } from "@/services/user-service";
import { useUserStore } from "@/stores/user-store";
import { removeAuthorization, setAuthorization } from "@/utils/authorization";
import { USER_INFO_QUERY_KEY } from "./use-user-info-request";

/**
 * Sign in and sign up as plain async calls, not TanStack mutations: a mutation would keep its variables, and so the
 * password, in the mutation cache (T-02-56). Credentials live only in the form until the request body is built.
 */
export function useAuthRequest() {
  const queryClient = useQueryClient();
  return useMemo(() => {
    async function signIn(email: string, password: string): Promise<void> {
      const { token } = await authService.login(email, password);
      setAuthorization(token);
      try {
        const user = await queryClient.fetchQuery({ queryKey: USER_INFO_QUERY_KEY, queryFn: getUserInfo, staleTime: 0 });
        useUserStore.getState().setUser(user);
      } catch (error) {
        // No half session: without a confirmed user the token is dropped again.
        removeAuthorization();
        throw error;
      }
    }
    /** Register, then sign in with the same credentials. */
    async function signUp(input: { email: string; password: string; nickname: string }): Promise<void> {
      await authService.register(input);
      await signIn(input.email, input.password);
    }
    return { signIn, signUp };
  }, [queryClient]);
}
