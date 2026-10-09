import { useQuery } from "@tanstack/react-query";
import { getDefaults, listModels, listProviders, type ModelType } from "@/services/model-service";
import { useActiveWorkspace } from "./use-workspaces";

/**
 * Query keys of the model settings data. Every key starts with `["ws", tenantId]`, so switching workspace never shows
 * another workspace's cache (D-26, T-03-20-04). Nothing cached under them holds a key: the API never returns one and
 * the mappers drop unknown fields; `dropSessionState` clears the whole cache on sign out.
 */
export const providersQueryKey = (tenantId: string | null) => ["ws", tenantId, "providers"] as const;
export const modelsQueryKey = (tenantId: string | null, type?: ModelType) => ["ws", tenantId, "models", type ?? "all"] as const;
export const defaultsQueryKey = (tenantId: string | null) => ["ws", tenantId, "defaults"] as const;

/** The workspace the model settings act in, or null while signed out. */
export function useModelTenantId(): string | null {
  return useActiveWorkspace()?.tenantId ?? null;
}

/** The active workspace's five providers with their models. No retry: a 503 or 403 is an answer, not a glitch. */
export function useProvidersRequest() {
  const tenantId = useModelTenantId();
  return useQuery({
    queryKey: providersQueryKey(tenantId),
    queryFn: () => listProviders(tenantId ?? ""),
    retry: false,
    enabled: tenantId !== null,
  });
}

/** The active workspace's models, optionally one type. */
export function useModelsRequest(type?: ModelType) {
  const tenantId = useModelTenantId();
  return useQuery({
    queryKey: modelsQueryKey(tenantId, type),
    queryFn: () => listModels(tenantId ?? "", type),
    retry: false,
    enabled: tenantId !== null,
  });
}

/** The active workspace's default chat and embedding model (composite ids, empty meaning not set). */
export function useDefaultsRequest() {
  const tenantId = useModelTenantId();
  return useQuery({
    queryKey: defaultsQueryKey(tenantId),
    queryFn: () => getDefaults(tenantId ?? ""),
    retry: false,
    enabled: tenantId !== null,
  });
}
