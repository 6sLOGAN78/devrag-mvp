import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, CanceledError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { getAuthorization, setAuthorization } from "@/utils/authorization";
import ModelsPage from ".";

// Drives the real Models page, dialogs, hooks, services and HTTP client against an in-memory server shaped like plan
// 03-12 (providers list, PUT save, POST instances, DELETE provider). The keys are obviously fake and assembled from parts.
const KEY = ["fake", "provider", "key", "7f3a"].join("-");
const OTHER_KEY = ["fake", "other", "key", "9c2e"].join("-");
const TOKEN = "tok-session";

const OWNER: SessionUser = {
  id: "u1",
  nickname: "Ada",
  email: "ada@example.test",
  avatar: "",
  language: "English",
  colorSchema: "Bright",
  tenantId: "t1",
  tenantName: "Ada's workspace",
  role: "owner",
  isSuperuser: false,
};

interface Row {
  tenant_id: string;
  tenant_name: string;
  owner_nickname: string;
  owner_avatar: string;
  role: string;
  joined_time: string;
}
const membership = (tenant: string, name: string, role: string): Row => ({ tenant_id: tenant, tenant_name: name, owner_nickname: "Ada", owner_avatar: "", role, joined_time: "2026-10-01T12:00:00Z" });
const stored = (rows: readonly Row[]) =>
  rows.map((r) => ({ tenantId: r.tenant_id, tenantName: r.tenant_name, ownerNickname: r.owner_nickname, ownerAvatar: r.owner_avatar, role: r.role, joinedTime: r.joined_time }));

interface Model {
  id: string;
  name: string;
  type: string;
  dimension: number | null;
  max_tokens: number;
  instance: string;
  used_tokens: number;
}
interface Instance {
  name: string;
  configured: boolean;
  models: string[];
  last4: string | null;
  base_url: string | null;
  api_version: string | null;
}
interface Provider {
  name: string;
  slug: string;
  configured: boolean;
  instances: Instance[];
  models: Model[];
}

const SLUGS = [
  ["OpenAI", "openai"],
  ["Azure-OpenAI", "azure-openai"],
  ["Ollama", "ollama"],
  ["OpenRouter", "openrouter"],
  ["OpenAI-Compatible", "openai-compatible"],
] as const;

const model = (provider: string, name: string, type: string): Model => ({
  id: `${name}@${provider}`,
  name,
  type,
  dimension: type === "embedding" ? 1024 : null,
  max_tokens: 8192,
  instance: "default",
  used_tokens: 0,
});

interface Seed {
  last4?: string | null;
  baseUrl?: string | null;
  apiVersion?: string | null;
  models: Array<[string, string]>;
}

function build(seeds: Record<string, Seed>): Provider[] {
  return SLUGS.map(([name, slug]) => {
    const seed = seeds[slug];
    if (seed === undefined) return { name, slug, configured: false, instances: [], models: [] };
    const models = seed.models.map(([n, type]) => model(name, n, type));
    const instance: Instance = {
      name: "default",
      configured: true,
      models: models.map((m) => m.id),
      last4: seed.last4 === undefined ? "ab12" : seed.last4,
      base_url: seed.baseUrl === undefined ? null : seed.baseUrl,
      api_version: seed.apiVersion === undefined ? null : seed.apiVersion,
    };
    return { name, slug, configured: true, instances: [instance], models };
  });
}

const OPENROUTER_SEED: Seed = {
  baseUrl: "https://openrouter.example.test/api/v1",
  models: [
    ["meta-llama/llama-3.1-8b-instruct", "chat"],
    ["baai/bge-m3", "embedding"],
  ],
};

interface Forced {
  status: number;
  code?: number;
  message?: string;
  reason?: string;
  headers?: Record<string, string>;
}

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let aborted: InternalAxiosRequestConfig[] = [];
let providers: Provider[] = [];
let memberships: Row[] = [];
let forced: Record<string, Forced> = {};
let hold: Promise<void> | null = null;
let defaults = { chat: "", embedding: "baai/bge-m3@OpenRouter" };

const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, f: Forced) {
  const data = f.reason === undefined ? null : { reason: f.reason };
  const response = { data: { code: f.code ?? (f.status === 400 ? 101 : f.status), message: f.message ?? "", data }, status: f.status, statusText: String(f.status), headers: new AxiosHeaders(f.headers ?? {}), config } as never;
  return Promise.reject(new AxiosError(`status ${f.status}`, "ERR_BAD_RESPONSE", config, null, response));
}

const bodyOf = (config: InternalAxiosRequestConfig): Record<string, unknown> => JSON.parse(String(config.data ?? "{}")) as Record<string, unknown>;
const view = (provider: Provider) => provider;
const isWrite = (config: InternalAxiosRequestConfig) => ["put", "post", "delete"].includes(String(config.method).toLowerCase()) && String(config.url).startsWith("/api/v1/providers");

function addModels(provider: Provider, models: Array<{ name: string; type: string }>): void {
  for (const m of models) {
    if (provider.models.some((existing) => existing.name === m.name)) continue;
    const added = model(provider.name, m.name, m.type);
    provider.models.push(added);
    provider.instances[0]?.models.push(added.id);
  }
}

function serve(config: InternalAxiosRequestConfig): unknown {
  const method = String(config.method).toUpperCase();
  const key = `${method} ${config.url}`;
  const stop = forced[key];
  if (stop) return failure(config, stop);
  if (key === "GET /v1/tenant/list") return ok(config, memberships);
  if (key === "GET /api/v1/providers") return ok(config, providers);
  if (key === "GET /api/v1/models/default") return ok(config, defaults);
  if (key === "PUT /api/v1/providers") {
    const body = bodyOf(config);
    const provider = providers.find((p) => p.slug === body.provider);
    if (!provider) return failure(config, { status: 400, reason: "provider_unknown", message: "unknown provider" });
    const instance = provider.instances[0] ?? { name: "default", configured: true, models: [], last4: null, base_url: null, api_version: null };
    instance.configured = true;
    if (typeof body.api_key === "string") instance.last4 = body.api_key.slice(-4);
    if (typeof body.base_url === "string") instance.base_url = body.base_url;
    if (typeof body.api_version === "string") instance.api_version = body.api_version;
    provider.instances = [instance];
    provider.configured = true;
    addModels(provider, body.models as Array<{ name: string; type: string }>);
    return ok(config, view(provider));
  }
  const instances = /^POST \/api\/v1\/providers\/([^/]+)\/instances$/.exec(key);
  if (instances) {
    const provider = providers.find((p) => p.slug === instances[1]);
    if (!provider || !provider.configured) return failure(config, { status: 404, message: "not found" });
    addModels(provider, bodyOf(config).models as Array<{ name: string; type: string }>);
    return ok(config, view(provider));
  }
  const removal = /^DELETE \/api\/v1\/providers\/([^/]+)$/.exec(key);
  if (removal) {
    const provider = providers.find((p) => p.slug === removal[1]);
    if (!provider) return failure(config, { status: 404, message: "not found" });
    provider.configured = false;
    provider.instances = [];
    provider.models = [];
    return ok(config, { deleted: true });
  }
  return failure(config, { status: 404, message: "not found" });
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  if (hold !== null && isWrite(config)) {
    const gate = hold;
    await new Promise<void>((resolve, reject) => {
      config.signal?.addEventListener?.("abort", () => {
        aborted.push(config);
        reject(new CanceledError("canceled", config));
      });
      void gate.then(resolve);
    });
  }
  return (await Promise.resolve(serve(config))) as never;
};

const writes = (method: string) => calls.filter((c) => String(c.method).toLowerCase() === method && String(c.url).startsWith("/api/v1/providers"));

let client: QueryClient;
function renderPage() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ModelsPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

const rowOf = (slug: string) => screen.getByTestId(`provider-row-${slug}`);
const dialog = () => screen.getByTestId("provider-dialog");

async function openFrom(slug: string, name: string) {
  const user = userEvent.setup();
  renderPage();
  await screen.findByTestId(`provider-row-${slug}`);
  await user.click(within(rowOf(slug)).getByRole("button", { name }));
  await screen.findByTestId("provider-dialog");
  return user;
}

function hostile(dump: unknown): string {
  return JSON.stringify(dump);
}

async function expectNoKeyRetained(secret = KEY) {
  await waitFor(() => {
    const mutations = hostile(client.getMutationCache().getAll().map((m) => m.state.variables ?? null));
    expect(mutations).not.toContain(secret);
  });
  const queries = hostile(client.getQueryCache().getAll().map((q) => [q.queryKey, q.state.data]));
  expect(queries).not.toContain(secret);
  expect(document.body.innerHTML).not.toContain(secret);
}

beforeEach(() => {
  calls = [];
  aborted = [];
  forced = {};
  hold = null;
  defaults = { chat: "", embedding: "baai/bge-m3@OpenRouter" };
  memberships = [membership("t1", "Ada's workspace", "owner")];
  providers = build({ openrouter: OPENROUTER_SEED });
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser(OWNER);
  useWorkspaceStore.getState().initialise("u1", "t1", stored(memberships));
  setAuthorization(TOKEN);
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("row actions (UI-37, D-07)", () => {
  it("shows the owner Set up on unconfigured providers and Add model, Change key and Delete on configured ones, with the provider in each name", async () => {
    providers = build({ openrouter: OPENROUTER_SEED, ollama: { last4: null, baseUrl: "http://localhost:11434", models: [["llama3.1", "chat"]] } });
    renderPage();
    await screen.findByTestId("provider-row-openai");
    expect(within(rowOf("openai")).getByRole("button", { name: "Set up OpenAI" })).toHaveTextContent("Set up");
    expect(within(rowOf("azure-openai")).getByRole("button", { name: "Set up Azure OpenAI" })).toBeInTheDocument();
    expect(within(rowOf("openai-compatible")).getByRole("button", { name: "Set up OpenAI-compatible" })).toBeInTheDocument();
    const openrouter = rowOf("openrouter");
    expect(within(openrouter).queryByRole("button", { name: /^Set up/ })).toBeNull();
    expect(within(openrouter).getByRole("button", { name: "Add a model to OpenRouter" })).toHaveTextContent("Add model");
    expect(within(openrouter).getByRole("button", { name: "Change the key for OpenRouter" })).toHaveTextContent("Change key");
    expect(within(openrouter).getByRole("button", { name: "Delete OpenRouter credentials" })).toBeInTheDocument();
    const ollama = rowOf("ollama");
    expect(within(ollama).getByRole("button", { name: "Change the address for Ollama" })).toHaveTextContent("Change address");
    expect(within(ollama).queryByRole("button", { name: /Change the key/ })).toBeNull();
  });

  it("shows an admin the same buttons", async () => {
    memberships = [membership("t1", "Ada's workspace", "admin")];
    useWorkspaceStore.getState().initialise("u1", "t1", stored(memberships));
    renderPage();
    await screen.findByTestId("provider-row-openai");
    expect(screen.getAllByTestId("provider-setup")).toHaveLength(4);
    expect(screen.getAllByTestId("provider-delete")).toHaveLength(1);
  });

  it("shows a member no button at all, not even a disabled one", async () => {
    memberships = [membership("t1", "Ada's workspace", "owner"), membership("t9", "Grace's workspace", "normal")];
    providers = build({ openrouter: { ...OPENROUTER_SEED, last4: null, baseUrl: null } });
    useWorkspaceStore.getState().initialise("u1", "t1", stored(memberships));
    useWorkspaceStore.getState().setActive("t9");
    renderPage();
    await screen.findByTestId("models-readonly-notice");
    await waitFor(() => expect(screen.getAllByTestId(/^provider-row-/)).toHaveLength(1));
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});

describe("set up dialog fields follow the provider table (D-15, UI-37)", () => {
  it("OpenAI asks for a key and two optional model ids, with no address field, and the key is a hardened password field", async () => {
    await openFrom("openai", "Set up OpenAI");
    expect(within(dialog()).getByRole("heading", { name: "Set up OpenAI" })).toBeInTheDocument();
    const key = screen.getByTestId("field-provider-key");
    expect(key).toHaveAttribute("type", "password");
    expect(key).toHaveAttribute("name", "provider_key");
    expect(key).toHaveAttribute("autocomplete", "off");
    expect(key).toHaveAttribute("spellcheck", "false");
    expect(key).toHaveAttribute("data-1p-ignore");
    expect(key).toHaveAttribute("data-lpignore", "true");
    expect(screen.getByLabelText("API key")).toBe(key);
    expect(screen.getByLabelText("Chat model")).toBe(screen.getByTestId("field-chat-model"));
    expect(screen.getByLabelText("Embedding model")).toBe(screen.getByTestId("field-embedding-model"));
    expect(screen.queryByTestId("field-base-url")).toBeNull();
    expect(screen.queryByTestId("field-api-version")).toBeNull();
    expect(within(dialog()).getAllByText(/The model id exactly as the provider names it, for example gpt-4o-mini\./)).toHaveLength(1);
    expect(within(dialog()).getByText(/for example text-embedding-3-small\./)).toBeInTheDocument();
    expect(screen.getByTestId("provider-submit")).toHaveTextContent("Test and save");
  });

  it("OpenRouter shows its own model examples", async () => {
    providers = build({});
    await openFrom("openrouter", "Set up OpenRouter");
    expect(within(dialog()).getByText(/for example meta-llama\/llama-3\.1-8b-instruct\./)).toBeInTheDocument();
    expect(within(dialog()).getByText(/for example baai\/bge-m3\./)).toBeInTheDocument();
    expect(screen.queryByTestId("field-base-url")).toBeNull();
  });

  it("Azure asks for an endpoint, an API version, a key and deployments", async () => {
    await openFrom("azure-openai", "Set up Azure OpenAI");
    expect(screen.getByLabelText("Endpoint")).toBe(screen.getByTestId("field-base-url"));
    expect(screen.getByLabelText("API version")).toBe(screen.getByTestId("field-api-version"));
    expect(screen.getByLabelText("API key")).toBe(screen.getByTestId("field-provider-key"));
    expect(screen.getByLabelText("Chat deployment")).toBe(screen.getByTestId("field-chat-model"));
    expect(screen.getByLabelText("Embedding deployment")).toBe(screen.getByTestId("field-embedding-model"));
  });

  it("Ollama asks for a base URL with a hint and has no key field", async () => {
    await openFrom("ollama", "Set up Ollama");
    expect(screen.getByLabelText("Base URL")).toBe(screen.getByTestId("field-base-url"));
    expect(within(dialog()).getByText("The server address without /v1, for example http://localhost:11434.")).toBeInTheDocument();
    expect(screen.queryByTestId("field-provider-key")).toBeNull();
    expect(screen.queryByTestId("field-api-version")).toBeNull();
  });

  it("OpenAI-compatible asks for a base URL and an optional key", async () => {
    await openFrom("openai-compatible", "Set up OpenAI-compatible");
    expect(screen.getByTestId("field-base-url")).toBeInTheDocument();
    expect(screen.getByTestId("field-provider-key")).toBeInTheDocument();
    expect(within(dialog()).getByText("Leave blank if the service needs no key.")).toBeInTheDocument();
  });

  it("refuses an empty submit on the client, names the missing parts and sends nothing", async () => {
    const user = await openFrom("openai", "Set up OpenAI");
    await user.click(screen.getByTestId("provider-submit"));
    expect(await within(dialog()).findByText("Enter the API key.")).toBeInTheDocument();
    expect(within(dialog()).getByText("Enter a chat model, an embedding model, or both.")).toBeInTheDocument();
    expect(writes("put")).toHaveLength(0);
  });

  it("rejects an Ollama address ending in /v1 before any request", async () => {
    const user = await openFrom("ollama", "Set up Ollama");
    await user.type(screen.getByTestId("field-base-url"), "http://localhost:11434/v1");
    await user.type(screen.getByTestId("field-chat-model"), "llama3.1");
    await user.click(screen.getByTestId("provider-submit"));
    expect(await within(dialog()).findByText("Use the server address without /v1 at the end.")).toBeInTheDocument();
    expect(writes("put")).toHaveLength(0);
  });
});

describe("test and save (D-16, D-17, T-03-21-01)", () => {
  async function fillOpenAi(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByTestId("field-provider-key"), KEY);
    await user.type(screen.getByTestId("field-chat-model"), "gpt-4o-mini");
  }

  it("sends PUT with the workspace, provider, key, models and a 45 second timeout, then closes, toasts and refreshes the list", async () => {
    const user = await openFrom("openai", "Set up OpenAI");
    const before = calls.filter((c) => c.url === "/api/v1/providers" && String(c.method).toLowerCase() === "get").length;
    await fillOpenAi(user);
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(screen.queryByTestId("provider-dialog")).toBeNull());
    const put = writes("put");
    expect(put).toHaveLength(1);
    expect(put[0]?.timeout).toBe(45000);
    expect(put[0]?.silent).toBe(true);
    expect(put[0]?.url).toBe("/api/v1/providers");
    expect(bodyOf(put[0]!)).toMatchObject({ tenant_id: "t1", provider: "openai", api_key: KEY, models: [{ name: "gpt-4o-mini", type: "chat" }] });
    expect(bodyOf(put[0]!)).not.toHaveProperty("base_url");
    expect(JSON.stringify(put[0]?.url) + JSON.stringify(put[0]?.params ?? null)).not.toContain(KEY);
    expect(await screen.findByText("OpenAI saved")).toBeInTheDocument();
    expect(screen.getByText("Choose default models below so datasets and chat can use them.")).toBeInTheDocument();
    await waitFor(() => expect(calls.filter((c) => c.url === "/api/v1/providers" && String(c.method).toLowerCase() === "get").length).toBeGreaterThan(before));
    await waitFor(() => expect(within(rowOf("openai")).getByTestId("provider-status")).toHaveTextContent("Configured"));
    expect(within(rowOf("openai")).getByTestId("provider-mask")).toHaveTextContent("••••••••7f3a");
    await expectNoKeyRetained();
  });

  it("leaves out the hint when the workspace already has a default of that type", async () => {
    defaults = { chat: "x@Y", embedding: "baai/bge-m3@OpenRouter" };
    const user = await openFrom("openai", "Set up OpenAI");
    await fillOpenAi(user);
    await user.click(screen.getByTestId("provider-submit"));
    expect(await screen.findByText("OpenAI saved")).toBeInTheDocument();
    expect(screen.queryByText("Choose default models below so datasets and chat can use them.")).toBeNull();
  });

  it("sends the address and version Azure asks for, and an embedding-only set up", async () => {
    const user = await openFrom("azure-openai", "Set up Azure OpenAI");
    await user.type(screen.getByTestId("field-base-url"), "https://res.example.test");
    await user.type(screen.getByTestId("field-api-version"), "2024-02-01");
    await user.type(screen.getByTestId("field-provider-key"), KEY);
    await user.type(screen.getByTestId("field-embedding-model"), "my-embedding");
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(writes("put")).toHaveLength(1));
    expect(bodyOf(writes("put")[0]!)).toMatchObject({
      provider: "azure-openai",
      base_url: "https://res.example.test",
      api_version: "2024-02-01",
      api_key: KEY,
      models: [{ name: "my-embedding", type: "embedding" }],
    });
  });

  it("sends no key for Ollama and no key field value for a blank optional key", async () => {
    const user = await openFrom("ollama", "Set up Ollama");
    await user.type(screen.getByTestId("field-base-url"), "http://localhost:11434");
    await user.type(screen.getByTestId("field-chat-model"), "llama3.1");
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(writes("put")).toHaveLength(1));
    const body = bodyOf(writes("put")[0]!);
    expect(body).toMatchObject({ provider: "ollama", base_url: "http://localhost:11434", models: [{ name: "llama3.1", type: "chat" }] });
    expect(body).not.toHaveProperty("api_key");
  });

  it("while pending marks the button busy and disabled, locks the fields, shows the 40 second status and sends one request", async () => {
    let release: () => void = () => undefined;
    hold = new Promise<void>((resolve) => (release = resolve));
    const user = await openFrom("openai", "Set up OpenAI");
    await fillOpenAi(user);
    const submit = screen.getByTestId("provider-submit");
    expect(screen.queryByTestId("provider-test-status")).toBeNull();
    await user.click(submit);
    await waitFor(() => expect(submit).toHaveAttribute("aria-busy", "true"));
    expect(submit).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("field-provider-key")).toHaveAttribute("readonly");
    expect(screen.getByTestId("field-chat-model")).toHaveAttribute("readonly");
    const status = screen.getByTestId("provider-test-status");
    expect(status).toHaveAttribute("role", "status");
    expect(status).toHaveTextContent("Testing the connection with a small request. This can take up to 40 seconds.");
    await user.click(submit);
    expect(writes("put")).toHaveLength(1);
    await act(async () => release());
    await waitFor(() => expect(screen.queryByTestId("provider-dialog")).toBeNull());
    expect(writes("put")).toHaveLength(1);
  });

  it("does not close on an overlay click while pending", async () => {
    let release: () => void = () => undefined;
    hold = new Promise<void>((resolve) => (release = resolve));
    const user = await openFrom("openai", "Set up OpenAI");
    await fillOpenAi(user);
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(screen.getByTestId("provider-submit")).toHaveAttribute("aria-busy", "true"));
    const overlay = document.querySelector('div[data-state="open"][aria-hidden="true"]');
    expect(overlay).not.toBeNull();
    fireEvent.pointerDown(overlay!);
    fireEvent.click(overlay!);
    expect(screen.getByTestId("provider-dialog")).toBeInTheDocument();
    await act(async () => release());
    await waitFor(() => expect(screen.queryByTestId("provider-dialog")).toBeNull());
  });

  it("aborts the request when Esc is pressed while pending, and nothing is saved", async () => {
    hold = new Promise<void>(() => undefined);
    const user = await openFrom("openai", "Set up OpenAI");
    await fillOpenAi(user);
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(screen.getByTestId("provider-submit")).toHaveAttribute("aria-busy", "true"));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("provider-dialog")).toBeNull());
    expect(aborted).toHaveLength(1);
    expect(aborted[0]?.method).toBe("put");
    expect(screen.queryByText("OpenAI saved")).toBeNull();
    expect(providers.find((p) => p.slug === "openai")?.configured).toBe(false);
    await expectNoKeyRetained();
  });

  it("aborts the request when Close is pressed while pending", async () => {
    hold = new Promise<void>(() => undefined);
    const user = await openFrom("openai", "Set up OpenAI");
    await fillOpenAi(user);
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(screen.getByTestId("provider-submit")).toHaveAttribute("aria-busy", "true"));
    await user.click(within(dialog()).getAllByRole("button", { name: "Close" })[0]!);
    await waitFor(() => expect(screen.queryByTestId("provider-dialog")).toBeNull());
    expect(aborted).toHaveLength(1);
  });

  it("clears the key when the dialog is closed and opened again", async () => {
    const user = await openFrom("openai", "Set up OpenAI");
    await user.type(screen.getByTestId("field-provider-key"), KEY);
    await user.type(screen.getByTestId("field-chat-model"), "gpt-4o-mini");
    await user.click(within(dialog()).getAllByRole("button", { name: "Close" })[0]!);
    await waitFor(() => expect(screen.queryByTestId("provider-dialog")).toBeNull());
    expect(document.body.innerHTML).not.toContain(KEY);
    await user.click(within(rowOf("openai")).getByRole("button", { name: "Set up OpenAI" }));
    await screen.findByTestId("provider-dialog");
    expect(screen.getByTestId("field-provider-key")).toHaveValue("");
    expect(screen.getByTestId("field-chat-model")).toHaveValue("");
  });

  it("keeps the key hidden until the person asks to see it", async () => {
    const user = await openFrom("openai", "Set up OpenAI");
    await user.type(screen.getByTestId("field-provider-key"), KEY);
    expect(screen.getByTestId("field-provider-key")).toHaveAttribute("type", "password");
    await user.click(screen.getByTestId("password-toggle"));
    expect(screen.getByTestId("field-provider-key")).toHaveAttribute("type", "text");
  });
});

describe("a refused configuration never ends the session (Pitfall 7, T-03-21-03)", () => {
  async function submitRefused(forcedAnswer: Forced) {
    forced["PUT /api/v1/providers"] = forcedAnswer;
    const user = await openFrom("openai", "Set up OpenAI");
    await user.type(screen.getByTestId("field-provider-key"), KEY);
    await user.type(screen.getByTestId("field-chat-model"), "gpt-4o-mini");
    await user.click(screen.getByTestId("provider-submit"));
    return user;
  }

  it("shows the provider's reason inline with the provider name, keeps the values and does not purgeSession, toast or retitle", async () => {
    const titleBefore = document.title;
    await submitRefused({ status: 400, reason: "provider_refused", message: "The provider rejected the key" });
    const alert = await screen.findByTestId("provider-refusal");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("OpenAI refused this configuration");
    expect(alert).toHaveTextContent("The provider rejected the key");
    expect(alert).toHaveAttribute("tabindex", "-1");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(screen.getByTestId("field-provider-key")).toHaveValue(KEY);
    expect(screen.getByTestId("field-provider-key")).toHaveAttribute("type", "password");
    expect(screen.getByTestId("field-chat-model")).toHaveValue("gpt-4o-mini");
    expect(screen.getByTestId("provider-submit")).not.toHaveAttribute("aria-busy");
    // the session is untouched: same token, same user, same page, no toast of any kind
    expect(getAuthorization()).toBe(TOKEN);
    expect(useUserStore.getState().user?.id).toBe("u1");
    expect(document.title).toBe(titleBefore);
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    expect(screen.queryByText(/Session expired/i)).toBeNull();
    expect(screen.getByTestId("models-page")).toBeInTheDocument();
  });

  it("uses the fallback sentence when the server gives no reason", async () => {
    await submitRefused({ status: 400, reason: "provider_refused", message: "" });
    const alert = await screen.findByTestId("provider-refusal");
    expect(alert).toHaveTextContent("Check the key, the base URL and the model ids, then try again.");
  });

  it("shows a long server text as a text node, bounded", async () => {
    await submitRefused({ status: 400, reason: "provider_refused", message: `<img src=x onerror=alert(1)> ${"x".repeat(400)}` });
    const alert = await screen.findByTestId("provider-refusal");
    expect(alert.querySelector("img")).toBeNull();
    expect(alert).toHaveTextContent("Check the key, the base URL and the model ids, then try again.");
    expectNoLongServerText();
  });

  it("renders markup in a short reason as text, never as elements", async () => {
    await submitRefused({ status: 400, reason: "provider_refused", message: "<b>bad</b> key" });
    const alert = await screen.findByTestId("provider-refusal");
    expect(alert.querySelector("b")).toBeNull();
    expect(alert).toHaveTextContent("<b>bad</b> key");
  });

  it("still ends the session on a real 401, because the shared interceptor has no bypass", async () => {
    await submitRefused({ status: 401, code: 401, message: "Unauthorized" });
    await waitFor(() => expect(getAuthorization()).toBeNull());
  });

  it.each([
    [{ status: 429, reason: "provider_test_rate_limited", message: "too many" }, "Too many tests in a short time. Wait a moment and try again."],
    [{ status: 503, reason: "provider_rate_limited", message: "busy", headers: { "retry-after": "1" } }, "The provider is busy right now. Wait a moment and try again."],
    [{ status: 503, reason: "key_store_unavailable", message: "no store" }, "Model settings aren't available right now. If it keeps failing, check System status."],
    [{ status: 504, reason: "provider_timeout", message: "slow" }, "The provider didn't answer in time. Nothing was saved. Try again."],
    [{ status: 502, reason: "provider_unreachable", message: "down" }, "The provider couldn't be reached. Nothing was saved. Try again."],
    [{ status: 403, message: "forbidden" }, "You don't have permission to do that in Ada's workspace. Your role may have changed."],
    [{ status: 500, message: "boom" }, "The configuration wasn't saved. Try again."],
  ] as Array<[Forced, string]>)("shows its own copy for %j", async (answer, copy) => {
    await submitRefused(answer);
    const alert = await screen.findByTestId("provider-error");
    expect(alert).toHaveTextContent(copy);
    expect(alert.textContent).not.toMatch(/session|sign in|unauthori[sz]ed/i);
    expect(screen.queryByTestId("provider-refusal")).toBeNull();
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    expect(getAuthorization()).toBe(TOKEN);
    expect(screen.getByTestId("field-provider-key")).toHaveValue(KEY);
  });
});

describe("change key (D-17, plan 03-10 and 03-12 contract)", () => {
  it("shows the saved tail in the helper, a blank key and no model field, and sends one registered chat model with the new key and no address", async () => {
    const user = await openFrom("openrouter", "Change the key for OpenRouter");
    expect(within(dialog()).getByRole("heading", { name: "Change the key for OpenRouter" })).toBeInTheDocument();
    expect(within(dialog()).getByText("The saved key ending ab12 is replaced. A saved key can't be shown again.")).toBeInTheDocument();
    expect(screen.getByTestId("field-provider-key")).toHaveValue("");
    expect(screen.queryByTestId("field-chat-model")).toBeNull();
    expect(screen.queryByTestId("field-embedding-model")).toBeNull();
    expect(screen.queryByTestId("field-base-url")).toBeNull();
    expect(dialog().innerHTML).not.toContain("openrouter.example.test");
    await user.type(screen.getByTestId("field-provider-key"), OTHER_KEY);
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(screen.queryByTestId("provider-dialog")).toBeNull());
    const put = writes("put");
    expect(put).toHaveLength(1);
    const body = bodyOf(put[0]!);
    expect(body).toEqual({
      tenant_id: "t1",
      provider: "openrouter",
      instance_name: "default",
      api_key: OTHER_KEY,
      models: [{ name: "meta-llama/llama-3.1-8b-instruct", type: "chat" }],
    });
    expect(put[0]?.timeout).toBe(45000);
    expect(await screen.findByText("OpenRouter updated")).toBeInTheDocument();
    expect(screen.queryByText("Choose default models below so datasets and chat can use them.")).toBeNull();
    await waitFor(() => expect(within(rowOf("openrouter")).getByTestId("provider-mask")).toHaveTextContent("••••••••9c2e"));
    await expectNoKeyRetained(OTHER_KEY);
  });

  it("sends the first embedding model when the provider has no chat model", async () => {
    providers = build({ openrouter: { ...OPENROUTER_SEED, models: [["baai/bge-m3", "embedding"], ["intfloat/e5", "embedding"]] } });
    const user = await openFrom("openrouter", "Change the key for OpenRouter");
    await user.type(screen.getByTestId("field-provider-key"), OTHER_KEY);
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(writes("put")).toHaveLength(1));
    expect(bodyOf(writes("put")[0]!).models).toEqual([{ name: "baai/bge-m3", type: "embedding" }]);
  });

  it("requires a typed key and sends nothing without one", async () => {
    const user = await openFrom("openrouter", "Change the key for OpenRouter");
    await user.click(screen.getByTestId("provider-submit"));
    expect(await within(dialog()).findByText("Enter the API key.")).toBeInTheDocument();
    expect(writes("put")).toHaveLength(0);
  });

  it("shows the server's key_required_for_new_address answer as the key field error", async () => {
    forced["PUT /api/v1/providers"] = { status: 400, reason: "key_required_for_new_address", message: "enter the key again to use a different address" };
    const user = await openFrom("openrouter", "Change the key for OpenRouter");
    await user.type(screen.getByTestId("field-provider-key"), OTHER_KEY);
    await user.click(screen.getByTestId("provider-submit"));
    expect(await within(dialog()).findByText("Enter the API key again to use a different address.")).toBeInTheDocument();
    expect(screen.queryByTestId("provider-refusal")).toBeNull();
    expect(screen.queryByTestId("provider-error")).toBeNull();
    expect(screen.getByTestId("field-provider-key")).toHaveAttribute("aria-invalid", "true");
  });

  it("OpenAI-compatible resends the stored address and refuses a changed address without a newly typed key, before any request", async () => {
    providers = build({ "openai-compatible": { last4: "wxyz", baseUrl: "https://old.example.test/v1", models: [["my-chat", "chat"]] } });
    const user = await openFrom("openai-compatible", "Change the key for OpenAI-compatible");
    expect(within(dialog()).getByText("Leave blank if the service needs no key. A saved key is never reused with a new address.")).toBeInTheDocument();
    const url = screen.getByTestId("field-base-url");
    expect(url).toHaveValue("https://old.example.test/v1");
    await user.clear(url);
    await user.type(url, "https://new.example.test/v1");
    await user.click(screen.getByTestId("provider-submit"));
    expect(await within(dialog()).findByText("Enter the API key again to use a different address.")).toBeInTheDocument();
    expect(writes("put")).toHaveLength(0);
    await user.type(screen.getByTestId("field-provider-key"), OTHER_KEY);
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(writes("put")).toHaveLength(1));
    expect(bodyOf(writes("put")[0]!)).toEqual({
      tenant_id: "t1",
      provider: "openai-compatible",
      instance_name: "default",
      api_key: OTHER_KEY,
      base_url: "https://new.example.test/v1",
      models: [{ name: "my-chat", type: "chat" }],
    });
  });

  it("Azure resends the stored endpoint and API version together with the new key", async () => {
    providers = build({ "azure-openai": { last4: "azur", baseUrl: "https://res.example.test", apiVersion: "2024-02-01", models: [["dep-1", "chat"]] } });
    const user = await openFrom("azure-openai", "Change the key for Azure OpenAI");
    expect(screen.getByTestId("field-base-url")).toHaveValue("https://res.example.test");
    expect(screen.getByTestId("field-api-version")).toHaveValue("2024-02-01");
    await user.type(screen.getByTestId("field-provider-key"), OTHER_KEY);
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(writes("put")).toHaveLength(1));
    expect(bodyOf(writes("put")[0]!)).toEqual({
      tenant_id: "t1",
      provider: "azure-openai",
      instance_name: "default",
      api_key: OTHER_KEY,
      base_url: "https://res.example.test",
      api_version: "2024-02-01",
      models: [{ name: "dep-1", type: "chat" }],
    });
  });
});

describe("change address (Ollama)", () => {
  it("renders only the base URL, sends the new address with no key and one registered model, and shows the new address in the row", async () => {
    providers = build({ ollama: { last4: null, baseUrl: "http://localhost:11434", models: [["llama3.1", "chat"], ["nomic-embed-text", "embedding"]] } });
    const user = await openFrom("ollama", "Change the address for Ollama");
    expect(within(dialog()).getByRole("heading", { name: "Change the address for Ollama" })).toBeInTheDocument();
    expect(screen.queryByTestId("field-provider-key")).toBeNull();
    expect(screen.queryByTestId("field-chat-model")).toBeNull();
    expect(screen.queryByTestId("field-embedding-model")).toBeNull();
    const url = screen.getByTestId("field-base-url");
    expect(url).toHaveValue("http://localhost:11434");
    await user.clear(url);
    await user.type(url, "http://ollama.example.test:11434");
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(screen.queryByTestId("provider-dialog")).toBeNull());
    const body = bodyOf(writes("put")[0]!);
    expect(body).toEqual({
      tenant_id: "t1",
      provider: "ollama",
      instance_name: "default",
      base_url: "http://ollama.example.test:11434",
      models: [{ name: "llama3.1", type: "chat" }],
    });
    expect(body).not.toHaveProperty("api_key");
    expect(await screen.findByText("Ollama updated")).toBeInTheDocument();
    await waitFor(() => expect(within(rowOf("ollama")).getByText("http://ollama.example.test:11434")).toBeInTheDocument());
  });

  it("refuses an empty address on the client", async () => {
    providers = build({ ollama: { last4: null, baseUrl: "http://localhost:11434", models: [["llama3.1", "chat"]] } });
    const user = await openFrom("ollama", "Change the address for Ollama");
    await user.clear(screen.getByTestId("field-base-url"));
    await user.click(screen.getByTestId("provider-submit"));
    expect(await within(dialog()).findByText("Enter the base URL.")).toBeInTheDocument();
    expect(writes("put")).toHaveLength(0);
  });
});

describe("add model (checker flag 10)", () => {
  it("tests and stores one more model through POST /providers/{provider}/instances", async () => {
    const user = await openFrom("openrouter", "Add a model to OpenRouter");
    expect(within(dialog()).getByRole("heading", { name: "Add a model to OpenRouter" })).toBeInTheDocument();
    expect(screen.queryByTestId("field-provider-key")).toBeNull();
    await user.type(screen.getByLabelText("Model id"), "intfloat/e5-large");
    await user.selectOptions(screen.getByLabelText("Type"), "embedding");
    await user.click(screen.getByTestId("provider-submit"));
    await waitFor(() => expect(screen.queryByTestId("provider-dialog")).toBeNull());
    const post = writes("post");
    expect(post).toHaveLength(1);
    expect(post[0]?.url).toBe("/api/v1/providers/openrouter/instances");
    expect(post[0]?.timeout).toBe(45000);
    expect(bodyOf(post[0]!)).toEqual({ tenant_id: "t1", instance_name: "default", models: [{ name: "intfloat/e5-large", type: "embedding" }] });
    expect(await screen.findByText("Model added")).toBeInTheDocument();
    await waitFor(() => expect(within(rowOf("openrouter")).getAllByTestId("model-row")).toHaveLength(3));
  });

  it("checks the model id before sending", async () => {
    const user = await openFrom("openrouter", "Add a model to OpenRouter");
    await user.click(screen.getByTestId("provider-submit"));
    expect(await within(dialog()).findByText("Enter the model id.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Model id"), "bad id");
    await user.click(screen.getByTestId("provider-submit"));
    expect(await within(dialog()).findByText("Model ids can't contain spaces or @.")).toBeInTheDocument();
    expect(writes("post")).toHaveLength(0);
  });

  it("shows a refusal inline with the provider's reason and no toast", async () => {
    forced["POST /api/v1/providers/openrouter/instances"] = { status: 400, reason: "provider_refused", message: "No such model" };
    const user = await openFrom("openrouter", "Add a model to OpenRouter");
    await user.type(screen.getByLabelText("Model id"), "nope/nothing");
    await user.click(screen.getByTestId("provider-submit"));
    const alert = await screen.findByTestId("provider-refusal");
    expect(alert).toHaveTextContent("OpenRouter refused this configuration");
    expect(alert).toHaveTextContent("No such model");
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    expect(getAuthorization()).toBe(TOKEN);
  });

  it("says a model that is already added is already added", async () => {
    forced["POST /api/v1/providers/openrouter/instances"] = { status: 409, reason: "model_exists", message: "that model is already added" };
    const user = await openFrom("openrouter", "Add a model to OpenRouter");
    await user.type(screen.getByLabelText("Model id"), "baai/bge-m3");
    await user.click(screen.getByTestId("provider-submit"));
    expect(await screen.findByTestId("provider-error")).toHaveTextContent("That model is already added.");
  });
});

describe("delete provider credentials (checker flag 4)", () => {
  it("opens an alert dialog with the plural body and focus on Keep provider, and Keep closes it without a request", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("provider-row-openrouter");
    await user.click(within(rowOf("openrouter")).getByRole("button", { name: "Delete OpenRouter credentials" }));
    const confirm = await screen.findByRole("alertdialog");
    expect(confirm).toHaveAttribute("data-testid", "provider-delete-dialog");
    expect(within(confirm).getByRole("heading", { name: "Delete OpenRouter credentials?" })).toBeInTheDocument();
    expect(confirm).toHaveTextContent("The saved credentials and the 2 models from OpenRouter are removed from Ada's workspace.");
    expect(confirm).toHaveTextContent("This can't be undone.");
    await waitFor(() => expect(within(confirm).getByRole("button", { name: "Keep provider" })).toHaveFocus());
    await user.click(within(confirm).getByRole("button", { name: "Keep provider" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(writes("delete")).toHaveLength(0);
  });

  it("uses the singular for one model", async () => {
    providers = build({ ollama: { last4: null, baseUrl: "http://localhost:11434", models: [["llama3.1", "chat"]] } });
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("provider-row-ollama");
    await user.click(within(rowOf("ollama")).getByRole("button", { name: "Delete Ollama credentials" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("The saved credentials and the 1 model from Ollama are removed from Ada's workspace.");
  });

  it("deletes with the workspace as a query parameter, toasts, refreshes the row and moves focus to the Providers title", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("provider-row-openrouter");
    await user.click(within(rowOf("openrouter")).getByRole("button", { name: "Delete OpenRouter credentials" }));
    await user.click(await screen.findByRole("button", { name: "Delete provider" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    const removal = writes("delete");
    expect(removal).toHaveLength(1);
    expect(removal[0]?.url).toBe("/api/v1/providers/openrouter");
    expect(removal[0]?.params).toEqual({ tenant_id: "t1" });
    expect(await screen.findByText("OpenRouter credentials deleted")).toBeInTheDocument();
    await waitFor(() => expect(within(rowOf("openrouter")).getByTestId("provider-status")).toHaveTextContent("Not configured"));
    await waitFor(() => expect(screen.getByRole("heading", { level: 2, name: "Providers" })).toHaveFocus());
  });

  it("shows the failure inline, keeps the dialog open and removes nothing", async () => {
    forced["DELETE /api/v1/providers/openrouter"] = { status: 500, message: "boom" };
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("provider-row-openrouter");
    await user.click(within(rowOf("openrouter")).getByRole("button", { name: "Delete OpenRouter credentials" }));
    await user.click(await screen.findByRole("button", { name: "Delete provider" }));
    const failure = await screen.findByTestId("provider-delete-error");
    expect(failure).toHaveTextContent("The credentials weren't deleted. Nothing was removed. Try again.");
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    expect(within(rowOf("openrouter")).getByTestId("provider-status")).toHaveTextContent("Configured");
  });
});

function expectNoLongServerText(): void {
  // The over-long reason is replaced by the fallback sentence, so none of its characters can reach the page.
  expect(document.body.innerHTML).not.toContain("x".repeat(100));
}
