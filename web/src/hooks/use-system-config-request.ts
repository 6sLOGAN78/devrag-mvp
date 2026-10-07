import { useQuery } from "@tanstack/react-query";
import { getSystemConfig } from "@/services/system-service";

export const SYSTEM_CONFIG_QUERY_KEY = ["system", "config"] as const;

/**
 * Server settings the signed-out pages need. `registerEnabled` is true only after the server says so: while loading
 * and on any failure it is false, so sign-up fails closed (D-01).
 */
export function useSystemConfigRequest() {
  const query = useQuery({ queryKey: SYSTEM_CONFIG_QUERY_KEY, queryFn: getSystemConfig, staleTime: 60_000, retry: false });
  return { registerEnabled: query.data?.registerEnabled === true, isLoading: query.isPending, isError: query.isError };
}
