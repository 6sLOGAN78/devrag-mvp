import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createApiToken, deleteApiToken, listApiTokens, type ApiToken } from "@/services/api-token-service";

/** The key never carries a token value. Cached rows hold token values, so `purgeSession` clears them on sign out. */
export const API_TOKENS_QUERY_KEY = ["api-tokens"] as const;

/** The workspace's tokens. No retry: a 403 (non-owner) is an answer, not a glitch. */
export function useApiTokensRequest(enabled = true) {
  return useQuery({ queryKey: API_TOKENS_QUERY_KEY, queryFn: listApiTokens, retry: false, enabled });
}

/** Creates a token and puts it at the top of the cached list. `gcTime: 0` drops the mutation result as soon as it is unobserved. */
export function useCreateApiToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createApiToken,
    gcTime: 0,
    onSuccess: (created) => {
      queryClient.setQueryData<ApiToken[]>(API_TOKENS_QUERY_KEY, (cached) => (cached === undefined ? cached : [created, ...cached.filter((t) => t.token !== created.token)]));
      void queryClient.invalidateQueries({ queryKey: API_TOKENS_QUERY_KEY });
    },
  });
}

/** Deletes one token. The list is refreshed whatever the outcome, so a token that is already gone (404) just disappears. */
export function useDeleteApiToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteApiToken,
    gcTime: 0,
    onSuccess: (_data, token) => {
      queryClient.setQueryData<ApiToken[]>(API_TOKENS_QUERY_KEY, (cached) => cached?.filter((t) => t.token !== token));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: API_TOKENS_QUERY_KEY }),
  });
}
