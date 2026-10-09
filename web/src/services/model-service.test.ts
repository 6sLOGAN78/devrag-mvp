import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { http } from "./http";
import { getDefaults, listModels, listProviders } from "./model-service";

const originalAdapter = http.defaults.adapter;
let body: unknown;
let seen: InternalAxiosRequestConfig[] = [];

const adapter: AxiosAdapter = (config) => {
  seen.push(config);
  return Promise.resolve({ data: body, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;
};

beforeEach(() => {
  seen = [];
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
});

const success = (data: unknown) => ({ code: 0, message: "", data });

const providerDto = {
  name: "OpenRouter",
  slug: "openrouter",
  configured: true,
  instances: [{ name: "default", configured: true, models: ["baai/bge-m3@OpenRouter"], last4: "ab12", base_url: "https://openrouter.ai/api/v1", api_version: null }],
  models: [{ id: "baai/bge-m3@OpenRouter", name: "baai/bge-m3", type: "embedding", dimension: 1024, max_tokens: 8192, instance: "default", used_tokens: 7 }],
};

describe("model service mapping (T-03-20-01)", () => {
  it("maps providers to camelCase, sends tenant_id as a query parameter and stays silent", async () => {
    body = success([providerDto]);
    const rows = await listProviders("t1");
    expect(rows).toEqual([
      {
        name: "OpenRouter",
        slug: "openrouter",
        configured: true,
        instances: [{ name: "default", configured: true, models: ["baai/bge-m3@OpenRouter"], last4: "ab12", baseUrl: "https://openrouter.ai/api/v1", apiVersion: null }],
        models: [{ id: "baai/bge-m3@OpenRouter", name: "baai/bge-m3", provider: "OpenRouter", type: "embedding", dimension: 1024, maxTokens: 8192, instance: "default", usedTokens: 7 }],
      },
    ]);
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe("/api/v1/providers");
    expect(seen[0]?.params).toEqual({ tenant_id: "t1" });
    expect(seen[0]?.silent).toBe(true);
  });

  it("never lets an unknown field, such as a key, reach the mapped object", async () => {
    body = success([
      {
        ...providerDto,
        api_key: "sk-FAKE-should-never-appear",
        instances: [{ ...providerDto.instances[0], key: "sk-FAKE-instance-key", api_key: "sk-FAKE-instance-api-key" }],
        models: [{ ...providerDto.models[0], api_key: "sk-FAKE-model-key" }],
      },
    ]);
    const rows = await listProviders("t1");
    const text = JSON.stringify(rows);
    expect(text).not.toContain("sk-FAKE");
    expect(text).not.toContain("api_key");
    expect(Object.keys(rows[0]!).sort()).toEqual(["configured", "instances", "models", "name", "slug"]);
    expect(Object.keys(rows[0]!.instances[0]!).sort()).toEqual(["apiVersion", "baseUrl", "configured", "last4", "models", "name"]);
  });

  it("coerces non-string and missing values and gives null credential fields for a member view", async () => {
    body = success([{ name: 5, slug: null, configured: "yes", instances: [{ name: "default", configured: true, models: [1, "m@P"] }], models: [{ id: "m@P", name: "m", type: "chat", dimension: "x", max_tokens: null, instance: 3 }] }]);
    const [row] = await listProviders("t1");
    expect(row).toMatchObject({ name: "", slug: "", configured: false });
    expect(row?.instances[0]).toEqual({ name: "default", configured: true, models: ["m@P"], last4: null, baseUrl: null, apiVersion: null });
    expect(row?.models[0]).toMatchObject({ id: "m@P", dimension: null, maxTokens: 0, instance: "", usedTokens: 0 });
  });

  it("returns an empty list for a non-array body", async () => {
    body = success({ not: "a list" });
    await expect(listProviders("t1")).resolves.toEqual([]);
    body = success(null);
    await expect(listModels("t1")).resolves.toEqual([]);
  });

  it("lists models with their provider, optionally filtered by type", async () => {
    body = success([{ id: "m@P", name: "m", provider: "OpenAI", type: "chat", dimension: null, max_tokens: 4096, instance: "default", used_tokens: 0, api_key: "sk-FAKE" }]);
    const rows = await listModels("t9", "chat");
    expect(rows).toEqual([{ id: "m@P", name: "m", provider: "OpenAI", type: "chat", dimension: null, maxTokens: 4096, instance: "default", usedTokens: 0 }]);
    expect(seen[0]?.url).toBe("/api/v1/models");
    expect(seen[0]?.params).toEqual({ tenant_id: "t9", type: "chat" });
    await listModels("t9");
    expect(seen[1]?.params).toEqual({ tenant_id: "t9" });
  });

  it("reads the defaults as composite ids, empty meaning not set", async () => {
    body = success({ chat: "", embedding: "baai/bge-m3@OpenRouter" });
    await expect(getDefaults("t1")).resolves.toEqual({ chat: "", embedding: "baai/bge-m3@OpenRouter" });
    expect(seen[0]?.url).toBe("/api/v1/models/default");
    expect(seen[0]?.params).toEqual({ tenant_id: "t1" });
    body = success(null);
    await expect(getDefaults("t1")).resolves.toEqual({ chat: "", embedding: "" });
  });
});
