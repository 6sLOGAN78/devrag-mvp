import { modelsDefaultPath, modelsPath, providersPath } from "@/constants/api-paths";
import { request } from "./http";

/**
 * Read side of the model APIs (plans 03-12 and 03-13). Every mapper copies an explicit list of fields and nothing
 * else, so a field the server should never send (a key, a ciphertext) cannot reach component state (T-03-20-01).
 * Write calls arrive with the provider dialogs in plan 03-21.
 */

/** One registered model. `id` is the composite id (`model@provider`, or `model@instance@provider`) the selects use. */
export interface ModelView {
  id: string;
  name: string;
  /** Display name of the provider that serves the model; empty only if the server sent none. */
  provider: string;
  type: string;
  /** Embedding dimension, or null for a chat model. */
  dimension: number | null;
  maxTokens: number;
  instance: string;
  usedTokens: number;
}

/**
 * One credential set of a provider. `last4`, `baseUrl` and `apiVersion` are null unless the caller is an owner or an
 * admin session: the API withholds them from members and API tokens (D-17), and so does this type.
 */
export interface InstanceView {
  name: string;
  configured: boolean;
  /** Composite ids of the models on this instance. */
  models: string[];
  last4: string | null;
  baseUrl: string | null;
  apiVersion: string | null;
}

export interface ProviderView {
  name: string;
  slug: string;
  configured: boolean;
  instances: InstanceView[];
  models: ModelView[];
}

/** Composite model ids; the empty string means "not set". */
export interface DefaultsView {
  chat: string;
  embedding: string;
}

export type ModelType = "chat" | "embedding";

interface ModelDto {
  id: string;
  name: string;
  provider?: string;
  type: string;
  dimension: number | null;
  max_tokens: number;
  instance: string;
  used_tokens: number;
}

interface InstanceDto {
  name: string;
  configured: boolean;
  models: string[];
  last4?: string | null;
  base_url?: string | null;
  api_version?: string | null;
}

interface ProviderDto {
  name: string;
  slug: string;
  configured: boolean;
  instances: InstanceDto[];
  models: ModelDto[];
}

interface DefaultsDto {
  chat: string;
  embedding: string;
}

const text = (value: unknown): string => (typeof value === "string" ? value : "");
const optionalText = (value: unknown): string | null => (typeof value === "string" ? value : null);
const count = (value: unknown): number => (typeof value === "number" && Number.isFinite(value) ? value : 0);
const asArray = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const asRecord = (value: unknown): Record<string, unknown> => (typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {});

function toModel(raw: unknown, fallbackProvider: string): ModelView {
  const dto = asRecord(raw) as Partial<ModelDto>;
  return {
    id: text(dto.id),
    name: text(dto.name),
    provider: text(dto.provider) || fallbackProvider,
    type: text(dto.type),
    dimension: typeof dto.dimension === "number" && Number.isFinite(dto.dimension) ? dto.dimension : null,
    maxTokens: count(dto.max_tokens),
    instance: text(dto.instance),
    usedTokens: count(dto.used_tokens),
  };
}

function toInstance(raw: unknown): InstanceView {
  const dto = asRecord(raw) as Partial<InstanceDto>;
  return {
    name: text(dto.name),
    configured: dto.configured === true,
    models: asArray(dto.models).filter((id): id is string => typeof id === "string"),
    last4: optionalText(dto.last4),
    baseUrl: optionalText(dto.base_url),
    apiVersion: optionalText(dto.api_version),
  };
}

function toProvider(raw: unknown): ProviderView {
  const dto = asRecord(raw) as Partial<ProviderDto>;
  const name = text(dto.name);
  return {
    name,
    slug: text(dto.slug),
    configured: dto.configured === true,
    instances: asArray(dto.instances).map(toInstance),
    models: asArray(dto.models).map((model) => toModel(model, name)),
  };
}

/** GET /api/v1/providers: the workspace's providers, each with its instances and models. Silent: the card renders its own error. */
export async function listProviders(tenantId: string): Promise<ProviderView[]> {
  const rows = await request<unknown>({ url: providersPath, method: "GET", params: { tenant_id: tenantId } }, { silent: true });
  return asArray(rows).map(toProvider);
}

/** GET /api/v1/models: the workspace's models across providers, optionally one type. */
export async function listModels(tenantId: string, type?: ModelType): Promise<ModelView[]> {
  const params = type === undefined ? { tenant_id: tenantId } : { tenant_id: tenantId, type };
  const rows = await request<unknown>({ url: modelsPath, method: "GET", params }, { silent: true });
  return asArray(rows).map((model) => toModel(model, ""));
}

/** GET /api/v1/models/default: the explicit defaults, empty strings when none was chosen. */
export async function getDefaults(tenantId: string): Promise<DefaultsView> {
  const dto = await request<unknown>({ url: modelsDefaultPath, method: "GET", params: { tenant_id: tenantId } }, { silent: true });
  const record = asRecord(dto) as Partial<DefaultsDto>;
  return { chat: text(record.chat), embedding: text(record.embedding) };
}
