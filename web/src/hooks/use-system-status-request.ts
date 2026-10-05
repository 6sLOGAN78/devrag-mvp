import { useQuery } from "@tanstack/react-query";
import { fetchGoHealth, fetchPythonStatus } from "@/services/system-service";

export const SYSTEM_STATUS_REFETCH_MS = 15_000;

const options = { refetchInterval: SYSTEM_STATUS_REFETCH_MS, retry: 1 } as const;

/** Polls both engines. A rejected query means the engine is unreachable; requests are silent (no toast). */
export function useSystemStatusRequest() {
  const go = useQuery({ queryKey: ["system-status", "go"], queryFn: fetchGoHealth, ...options });
  const python = useQuery({ queryKey: ["system-status", "python"], queryFn: fetchPythonStatus, ...options });
  return {
    go,
    python,
    isFetching: go.isFetching || python.isFetching,
    refetch: () => Promise.all([go.refetch(), python.refetch()]),
  };
}
