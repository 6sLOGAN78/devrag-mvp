import { describe, expect, it } from "vitest";
import type { InstanceView, ModelView, ProviderView } from "@/services/model-service";
import { findProvider } from "./providers";
import { addModelSchema, providerSchema, type ProviderFormValues } from "./schemas";

// Obviously fake, assembled from parts so no scanner mistakes it for a credential.
const KEY = ["fake", "provider", "key", "0001"].join("-");

const blank: ProviderFormValues = { apiKey: "", baseUrl: "", apiVersion: "", chatModel: "", embeddingModel: "" };
const values = (patch: Partial<ProviderFormValues>): ProviderFormValues => ({ ...blank, ...patch });

function specOf(slug: string) {
  const spec = findProvider(slug);
  if (spec === undefined) throw new Error(`unknown provider ${slug}`);
  return spec;
}

/** `[field, message]` pairs for every issue; empty when the values are accepted. */
function issues(slug: string, mode: "setup" | "change", input: ProviderFormValues, current?: ProviderView): Array<[string, string]> {
  const result = providerSchema(specOf(slug), mode, current).safeParse(input);
  return result.success ? [] : result.error.issues.map((issue) => [String(issue.path[0]), issue.message]);
}

const model = (name: string, type: string): ModelView => ({ id: `${name}@P`, name, provider: "P", type, dimension: null, maxTokens: 0, instance: "default", usedTokens: 0 });
const instance = (patch: Partial<InstanceView>): InstanceView => ({ name: "default", configured: true, models: [], last4: "ab12", baseUrl: null, apiVersion: null, ...patch });
const view = (slug: string, instances: InstanceView[]): ProviderView => ({ name: slug, slug, configured: true, instances, models: [model("m", "chat")] });

describe("provider form rules in set up mode (UI-37)", () => {
  it("OpenAI needs a key and has no address field", () => {
    expect(issues("openai", "setup", values({ chatModel: "gpt-4o-mini" }))).toEqual([["apiKey", "errors.provider.keyRequired"]]);
    expect(issues("openai", "setup", values({ apiKey: KEY, chatModel: "gpt-4o-mini" }))).toEqual([]);
    // an address the form never shows is not validated
    expect(issues("openai", "setup", values({ apiKey: KEY, chatModel: "m", baseUrl: "not a url" }))).toEqual([]);
  });

  it("OpenRouter needs a key", () => {
    expect(issues("openrouter", "setup", values({ embeddingModel: "baai/bge-m3" }))).toEqual([["apiKey", "errors.provider.keyRequired"]]);
    expect(issues("openrouter", "setup", values({ apiKey: KEY, embeddingModel: "baai/bge-m3" }))).toEqual([]);
  });

  it("Azure needs an endpoint, an API version and a key", () => {
    expect(issues("azure-openai", "setup", values({ chatModel: "my-deployment" }))).toEqual([
      ["baseUrl", "errors.provider.baseUrlRequired"],
      ["apiVersion", "errors.provider.apiVersionRequired"],
      ["apiKey", "errors.provider.keyRequired"],
    ]);
    expect(issues("azure-openai", "setup", values({ baseUrl: "https://res.example.test", apiVersion: "2024-02-01", apiKey: KEY, chatModel: "d" }))).toEqual([]);
  });

  it("Ollama needs a base URL without /v1 and asks for no key", () => {
    expect(issues("ollama", "setup", values({ chatModel: "llama3.1" }))).toEqual([["baseUrl", "errors.provider.baseUrlRequired"]]);
    expect(issues("ollama", "setup", values({ baseUrl: "http://localhost:11434/v1", chatModel: "llama3.1" }))).toEqual([["baseUrl", "errors.provider.ollamaV1"]]);
    expect(issues("ollama", "setup", values({ baseUrl: "http://localhost:11434/v1/", chatModel: "llama3.1" }))).toEqual([["baseUrl", "errors.provider.ollamaV1"]]);
    expect(issues("ollama", "setup", values({ baseUrl: "http://localhost:11434", chatModel: "llama3.1" }))).toEqual([]);
  });

  it("OpenAI-compatible needs a base URL and allows an empty key", () => {
    expect(issues("openai-compatible", "setup", values({ chatModel: "m" }))).toEqual([["baseUrl", "errors.provider.baseUrlRequired"]]);
    expect(issues("openai-compatible", "setup", values({ baseUrl: "https://llm.example.test/v1", chatModel: "m" }))).toEqual([]);
    expect(issues("openai-compatible", "setup", values({ baseUrl: "https://llm.example.test/v1", chatModel: "m", apiKey: KEY }))).toEqual([]);
  });

  it.each([
    ["ftp://llm.example.test", "errors.provider.baseUrlInvalid"],
    ["llm.example.test", "errors.provider.baseUrlInvalid"],
    ["http:llm", "errors.provider.baseUrlInvalid"],
    ["https://", "errors.provider.baseUrlInvalid"],
    ["https://llm.example.test/v1#frag", "errors.provider.baseUrlInvalid"],
    ["https://user@llm.example.test/v1", "errors.provider.baseUrlCredentials"],
    ["https://user:pw@llm.example.test/v1", "errors.provider.baseUrlCredentials"],
  ])("refuses the base URL %s", (url, message) => {
    expect(issues("openai-compatible", "setup", values({ baseUrl: url, chatModel: "m" }))).toEqual([["baseUrl", message]]);
  });

  it("accepts an http URL with a port and a path", () => {
    expect(issues("openai-compatible", "setup", values({ baseUrl: "http://10.0.0.5:8000/v1", chatModel: "m" }))).toEqual([]);
  });

  it("requires at least one of the chat and embedding model, with the error under the second field", () => {
    expect(issues("openai", "setup", values({ apiKey: KEY }))).toEqual([["embeddingModel", "errors.provider.modelRequired"]]);
    expect(issues("openai", "setup", values({ apiKey: KEY, chatModel: "   ", embeddingModel: " " }))).toEqual([["embeddingModel", "errors.provider.modelRequired"]]);
    expect(issues("openai", "setup", values({ apiKey: KEY, embeddingModel: "text-embedding-3-small" }))).toEqual([]);
  });

  it("checks the model id: 1 to 128 characters, no whitespace, no @, slash and colon allowed", () => {
    const ok = (id: string) => issues("openrouter", "setup", values({ apiKey: KEY, chatModel: id }));
    expect(ok("meta-llama/llama-3.1-8b-instruct")).toEqual([]);
    expect(ok("llama3:8b")).toEqual([]);
    expect(ok("a".repeat(128))).toEqual([]);
    expect(ok("a".repeat(129))).toEqual([["chatModel", "errors.model.idMax"]]);
    expect(ok("has space")).toEqual([["chatModel", "errors.model.idInvalid"]]);
    expect(ok("tab\tid")).toEqual([["chatModel", "errors.model.idInvalid"]]);
    expect(ok("name@provider")).toEqual([["chatModel", "errors.model.idInvalid"]]);
    expect(issues("openrouter", "setup", values({ apiKey: KEY, embeddingModel: "x y" }))).toEqual([["embeddingModel", "errors.model.idInvalid"]]);
  });
});

describe("provider form rules in change mode", () => {
  it("renders no model fields, so no model is required and a stray value is ignored", () => {
    expect(issues("openrouter", "change", values({ apiKey: KEY }))).toEqual([]);
    expect(issues("openrouter", "change", values({ apiKey: KEY, chatModel: "has space" }))).toEqual([]);
  });

  it("requires the key for a provider whose key is required, even with the address unchanged", () => {
    expect(issues("openrouter", "change", values({}))).toEqual([["apiKey", "errors.provider.keyRequired"]]);
    expect(issues("openai", "change", values({}))).toEqual([["apiKey", "errors.provider.keyRequired"]]);
  });

  it("requires a newly typed key when the base URL changed for a keyed provider", () => {
    const current = view("openai-compatible", [instance({ last4: "wxyz", baseUrl: "https://old.example.test/v1" })]);
    expect(issues("openai-compatible", "change", values({ baseUrl: "https://new.example.test/v1" }), current)).toEqual([["apiKey", "errors.provider.keyNewAddress"]]);
    expect(issues("openai-compatible", "change", values({ baseUrl: "https://new.example.test/v1", apiKey: KEY }), current)).toEqual([]);
  });

  it("treats a trailing slash and surrounding space as the same address", () => {
    const current = view("openai-compatible", [instance({ last4: "wxyz", baseUrl: "https://old.example.test/v1" })]);
    expect(issues("openai-compatible", "change", values({ baseUrl: " https://old.example.test/v1/ " }), current)).toEqual([]);
  });

  it("requires a newly typed key when the Azure API version changed", () => {
    const current = view("azure-openai", [instance({ baseUrl: "https://res.example.test", apiVersion: "2024-02-01" })]);
    const next = values({ baseUrl: "https://res.example.test", apiVersion: "2024-06-01" });
    expect(issues("azure-openai", "change", next, current)).toEqual([["apiKey", "errors.provider.keyRequired"]]);
  });

  it("asks for no key when the provider has none and still validates the address", () => {
    const current = view("ollama", [instance({ last4: null, baseUrl: "http://localhost:11434" })]);
    expect(issues("ollama", "change", values({ baseUrl: "http://other:11434" }), current)).toEqual([]);
    expect(issues("ollama", "change", values({ baseUrl: "http://other:11434/v1" }), current)).toEqual([["baseUrl", "errors.provider.ollamaV1"]]);
    expect(issues("ollama", "change", values({ baseUrl: "" }), current)).toEqual([["baseUrl", "errors.provider.baseUrlRequired"]]);
  });

  it("lets a keyless OpenAI-compatible instance move to a new address without a key", () => {
    const current = view("openai-compatible", [instance({ last4: null, baseUrl: "https://old.example.test/v1" })]);
    expect(issues("openai-compatible", "change", values({ baseUrl: "https://new.example.test/v1" }), current)).toEqual([]);
  });
});

describe("add model rules", () => {
  const parse = (modelId: string, type = "chat") => {
    const result = addModelSchema.safeParse({ modelId, type });
    return result.success ? [] : result.error.issues.map((issue) => [String(issue.path[0]), issue.message]);
  };

  it("requires the model id and applies the same id rule", () => {
    expect(parse("")).toEqual([["modelId", "errors.model.idRequired"]]);
    expect(parse("   ")).toEqual([["modelId", "errors.model.idRequired"]]);
    expect(parse("a b")).toEqual([["modelId", "errors.model.idInvalid"]]);
    expect(parse("a@b")).toEqual([["modelId", "errors.model.idInvalid"]]);
    expect(parse("a".repeat(129))).toEqual([["modelId", "errors.model.idMax"]]);
    expect(parse("baai/bge-m3", "embedding")).toEqual([]);
  });

  it("accepts only the two model types", () => {
    expect(addModelSchema.safeParse({ modelId: "m", type: "image" }).success).toBe(false);
  });
});
