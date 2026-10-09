import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  addModel,
  deleteProvider,
  getDefaults,
  listModels,
  listProviders,
  saveProvider,
  type AddModelInput,
  type ModelType,
  type SaveProviderInput,
} from "@/services/model-service";
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

/**
 * Variables of the write mutations. `SaveProviderInput.apiKey` is the typed key: the mutation uses `gcTime: 0`, and the
 * dialog calls `reset()` once the call settles, so the variables (and the key in them) leave the mutation cache at
 * once. Nothing here logs, keys a query by, or stores the variables.
 */
export interface SaveProviderVariables {
  input: SaveProviderInput;
  signal?: AbortSignal;
}
export interface AddModelVariables {
  input: AddModelInput;
  signal?: AbortSignal;
}
export interface DeleteProviderVariables {
  tenantId: string;
  provider: string;
  signal?: AbortSignal;
}

/** Whatever the outcome, the workspace's provider, model and default data is refetched (a failed test may still have changed nothing, a timeout may have saved). */
function invalidateModelData(queryClient: QueryClient, tenantId: string): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: providersQueryKey(tenantId) }),
    queryClient.invalidateQueries({ queryKey: ["ws", tenantId, "models"] }),
    queryClient.invalidateQueries({ queryKey: defaultsQueryKey(tenantId) }),
  ]);
}

/** Tests and saves a provider (set up, change key, change address). Not retried: each attempt is a real provider call. */
export function useSaveProviderRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ input, signal }: SaveProviderVariables) => saveProvider(input, signal),
    retry: false,
    gcTime: 0,
    onSettled: (_data, _error, variables) => invalidateModelData(queryClient, variables.input.tenantId),
  });
}

/** Tests and adds one model to a configured provider. */
export function useAddModelRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ input, signal }: AddModelVariables) => addModel(input, signal),
    retry: false,
    gcTime: 0,
    onSettled: (_data, _error, variables) => invalidateModelData(queryClient, variables.input.tenantId),
  });
}

/** Removes a provider's credentials and models from the workspace. */
export function useDeleteProviderRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ tenantId, provider, signal }: DeleteProviderVariables) => deleteProvider(tenantId, provider, signal),
    retry: false,
    gcTime: 0,
    onSettled: (_data, _error, variables) => invalidateModelData(queryClient, variables.tenantId),
  });
}

/** Drops a settled mutation's variables from the cache. The dialogs call this in a `finally`, so a typed key never lingers. */
export function clearMutation(mutation: { reset: () => void }): void {
  mutation.reset();
}
