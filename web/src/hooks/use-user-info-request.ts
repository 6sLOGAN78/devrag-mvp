import { useQuery } from "@tanstack/react-query";
import { getUserInfo } from "@/services/user-service";
import { useAuthorization } from "./use-authorization";

export const USER_INFO_QUERY_KEY = ["user", "info"] as const;

/** Session recovery query (UI-07): runs only with a stored token, never retries, and stays fresh for the session. */
export function useUserInfoRequest() {
  const token = useAuthorization();
  return useQuery({
    queryKey: USER_INFO_QUERY_KEY,
    queryFn: getUserInfo,
    retry: false,
    staleTime: Infinity,
    enabled: token !== null,
  });
}
