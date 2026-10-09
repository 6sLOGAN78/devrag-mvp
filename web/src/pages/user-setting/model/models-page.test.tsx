import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";
import ModelsPage from ".";

// Drives the real page, hooks, services and HTTP client against an in-memory server shaped like plans 03-12 and 03-13:
// the provider list (credential fields only for owner and admin sessions), the model defaults and the membership list.
// Every key and address is obviously fake.
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
const OWN: Row = { tenant_id: "t1", tenant_name: "Ada's workspace", owner_nickname: "Ada", owner_avatar: "", role: "owner", joined_time: "2026-10-01T12:00:00Z" };
const joined = (role: string): Row => ({ tenant_id: "t9", tenant_name: "Grace's workspace", owner_nickname: "Grace", owner_avatar: "", role, joined_time: "2026-10-01T12:00:00Z" });

const SLUGS = [
  ["OpenAI", "openai"],
  ["Azure-OpenAI", "azure-openai"],
  ["Ollama", "ollama"],
  ["OpenRouter", "openrouter"],
  ["OpenAI-Compatible", "openai-compatible"],
] as const;

const EMBED = "baai/bge-m3@OpenRouter";
const CHAT = "meta-llama/llama-3.1-8b-instruct@OpenRouter";

/** The five provider rows the way the API serves them; `credentials` mirrors the owner and admin view. */
function providerList(options: { configured: readonly string[]; credentials: boolean }) {
  return SLUGS.map(([name, slug]) => {
    const on = options.configured.includes(slug);
    const models =
      on && slug === "openrouter"
        ? [
            { id: CHAT, name: "meta-llama/llama-3.1-8b-instruct", type: "chat", dimension: null, max_tokens: 8192, instance: "default", used_tokens: 0 },
            { id: EMBED, name: "baai/bge-m3", type: "embedding", dimension: 1024, max_tokens: 8192, instance: "default", used_tokens: 3 },
          ]
        : [];
    const instance = on
      ? {
          name: "default",
          configured: true,
          models: models.map((m) => m.id),
          ...(options.credentials ? { last4: "ab12", base_url: "https://openrouter.example.test/api/v1", api_version: null } : {}),
          // A hostile or buggy server field: the SPA must drop it before it reaches state or the DOM (T-03-20-01).
          api_key: "sk-FAKE-hostile-field-0000",
        }
      : null;
    return { name, slug, configured: on, instances: instance ? [instance] : [], models };
  });
}

interface Forced {
  status: number;
  message: string;
}

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let memberships: Row[] = [];
let forced: Record<string, Forced> = {};
let hold: Promise<void> | null = null;
let providersByTenant: Record<string, unknown>;
let defaultsByTenant: Record<string, { chat: string; embedding: string }>;

const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, f: Forced) {
  const response = { data: { code: f.status, message: f.message, data: null }, status: f.status, statusText: String(f.status), headers: new AxiosHeaders(), config } as never;
  return Promise.reject(new AxiosError(`status ${f.status}`, "ERR_BAD_RESPONSE", config, null, response));
}

const tenantOf = (config: InternalAxiosRequestConfig) => String((config.params as { tenant_id?: string } | undefined)?.tenant_id ?? "");

function serve(config: InternalAxiosRequestConfig): unknown {
  const key = `${String(config.method).toUpperCase()} ${config.url}`;
  const stop = forced[key];
  if (stop) return failure(config, stop);
  if (key === "GET /v1/tenant/list") return ok(config, memberships);
  if (key === "GET /api/v1/providers") return ok(config, providersByTenant[tenantOf(config)] ?? []);
  if (key === "GET /api/v1/models/default") return ok(config, defaultsByTenant[tenantOf(config)] ?? { chat: "", embedding: "" });
  return failure(config, { status: 404, message: "not found" });
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  if (hold && config.url === "/api/v1/providers") await hold;
  return (await Promise.resolve(serve(config))) as never;
};

const callsTo = (url: string) => calls.filter((c) => c.url === url);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ModelsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The memberships the way the store keeps them (camelCase), derived from the server rows. */
const stored = (rows: readonly Row[]) =>
  rows.map((r) => ({ tenantId: r.tenant_id, tenantName: r.tenant_name, ownerNickname: r.owner_nickname, ownerAvatar: r.owner_avatar, role: r.role, joinedTime: r.joined_time }));

const rowOf = (slug: string) => screen.getByTestId(`provider-row-${slug}`);

beforeEach(() => {
  calls = [];
  forced = {};
  hold = null;
  memberships = [OWN];
  providersByTenant = { t1: providerList({ configured: ["openrouter"], credentials: true }), t9: providerList({ configured: ["openrouter"], credentials: false }) };
  defaultsByTenant = { t1: { chat: "", embedding: EMBED }, t9: { chat: CHAT, embedding: EMBED } };
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser(OWNER);
  useWorkspaceStore.getState().initialise("u1", "t1", stored([OWN]));
  setAuthorization("tok-session");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("Models page structure (UI-37, D-15)", () => {
  it("makes Models the first heading, sets the title and names the active workspace in the intro", async () => {
    renderPage();
    const page = screen.getByTestId("models-page");
    expect(within(page).getByRole("heading", { level: 1, name: "Models" })).toBe(within(page).getAllByRole("heading")[0]);
    expect(document.title).toBe("Models - devRag");
    expect(within(page).getByText("Model providers and default models for Ada's workspace.")).toBeInTheDocument();
    await screen.findByTestId("provider-row-openai");
  });

  it("lists the five providers in the fixed order with a status badge and a description each", async () => {
    renderPage();
    await screen.findByTestId("provider-row-openai");
    const ids = screen.getAllByTestId(/^provider-row-/).map((el) => el.getAttribute("data-testid"));
    expect(ids).toEqual(["provider-row-openai", "provider-row-azure-openai", "provider-row-ollama", "provider-row-openrouter", "provider-row-openai-compatible"]);
    expect(within(rowOf("openai")).getByText("OpenAI")).toBeInTheDocument();
    expect(within(rowOf("azure-openai")).getByText("Azure OpenAI")).toBeInTheDocument();
    expect(within(rowOf("openai-compatible")).getByText("OpenAI-compatible")).toBeInTheDocument();
    expect(within(rowOf("openai")).getByTestId("provider-status")).toHaveTextContent("Not configured");
    expect(within(rowOf("openrouter")).getByTestId("provider-status")).toHaveTextContent("Configured");
    expect(within(rowOf("openai")).getByText("Chat and embedding models from OpenAI.")).toBeInTheDocument();
    expect(within(rowOf("openrouter")).getByText("Many chat and embedding models behind one key.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Providers" })).toBeInTheDocument();
  });

  it("renders the write actions for an owner: Set up on the four unconfigured rows, Add model, Change key and Delete on the configured one", async () => {
    renderPage();
    await screen.findByTestId("provider-row-openai");
    expect(screen.getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
      "Set up OpenAI",
      "Set up Azure OpenAI",
      "Set up Ollama",
      "Add a model to OpenRouter",
      "Change the key for OpenRouter",
      "Delete OpenRouter credentials",
      "Set up OpenAI-compatible",
    ]);
  });

describe("Owner and admin view (D-07, D-17)", () => {
  it("shows the masked key, the base URL and the models with type, dimensions and the default badge", async () => {
    renderPage();
    await screen.findByTestId("provider-row-openai");
    const row = await waitFor(() => {
      const el = rowOf("openrouter");
      expect(within(el).getAllByTestId("model-row")).toHaveLength(2);
      return el;
    });
    expect(within(row).getByTestId("provider-mask")).toHaveTextContent("••••••••ab12");
    expect(within(row).getByText("https://openrouter.example.test/api/v1")).toBeInTheDocument();
    const models = within(row).getAllByTestId("model-row");
    expect(models[0]).toHaveTextContent("meta-llama/llama-3.1-8b-instruct");
    expect(models[0]).toHaveTextContent("Chat");
    expect(models[0]).not.toHaveTextContent("Default chat");
    expect(models[1]).toHaveTextContent("baai/bge-m3");
    expect(models[1]).toHaveTextContent("Embedding");
    expect(models[1]).toHaveTextContent("1024 dimensions");
    expect(models[1]).toHaveTextContent("Default embedding");
  });

  it("shows no credential line on a provider that is not configured and no read-only notice", async () => {
    renderPage();
    await screen.findByTestId("provider-row-openai");
    expect(within(rowOf("openai")).queryByTestId("provider-mask")).toBeNull();
    expect(screen.queryByTestId("models-readonly-notice")).toBeNull();
  });

  it("never renders anything resembling a saved key", async () => {
    renderPage();
    await screen.findByTestId("provider-row-openai");
    await waitFor(() => expect(within(rowOf("openrouter")).getAllByTestId("model-row")).toHaveLength(2));
    expect(screen.getByTestId("models-page").innerHTML).not.toMatch(/sk-/);
    expect(document.querySelectorAll("input")).toHaveLength(0);
    expect(screen.queryByTestId("provider-dialog")).toBeNull();
  });
});

describe("Member view (D-17, D-26)", () => {
  beforeEach(() => {
    memberships = [OWN, joined("normal")];
    useWorkspaceStore.getState().initialise("u1", "t1", stored(memberships));
    useWorkspaceStore.getState().setActive("t9");
  });

  it("shows only configured providers, no mask, no last four and no address, and the read-only notice", async () => {
    renderPage();
    const notice = await screen.findByTestId("models-readonly-notice");
    expect(notice).toHaveAttribute("role", "status");
    expect(notice).toHaveTextContent("Only the workspace owner and admins can change model settings.");
    await waitFor(() => expect(screen.getAllByTestId(/^provider-row-/)).toHaveLength(1));
    expect(screen.getByTestId("provider-row-openrouter")).toBeInTheDocument();
    expect(screen.queryByTestId("provider-mask")).toBeNull();
    const html = screen.getByTestId("models-page").innerHTML;
    expect(html).not.toContain("ab12");
    expect(html).not.toContain("openrouter.example.test");
    expect(screen.getByText("Model providers and default models for Grace's workspace.")).toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("sends the active workspace id on every request", async () => {
    renderPage();
    await screen.findByTestId("models-readonly-notice");
    await waitFor(() => expect(callsTo("/api/v1/providers").some((c) => tenantOf(c) === "t9")).toBe(true));
    expect(callsTo("/api/v1/models/default").every((c) => tenantOf(c) === "t9" || tenantOf(c) === "t1")).toBe(true);
    expect(callsTo("/api/v1/providers").at(-1)?.params).toEqual({ tenant_id: "t9" });
  });

  it("shows 'No models configured yet' when nothing is configured", async () => {
    providersByTenant.t9 = providerList({ configured: [], credentials: false });
    renderPage();
    await screen.findByTestId("models-readonly-notice");
    expect(await screen.findByRole("heading", { level: 2, name: "No models configured yet" })).toBeInTheDocument();
    expect(screen.getByText("Ask the workspace owner or an admin to add a model provider.")).toBeInTheDocument();
    expect(screen.queryAllByTestId(/^provider-row-/)).toHaveLength(0);
  });
});

describe("Workspace switching (D-26)", () => {
  it("changes the page when the active workspace changes: other data, other role", async () => {
    memberships = [OWN, joined("normal")];
    renderPage();
    await screen.findByTestId("provider-row-openai");
    expect(screen.queryByTestId("models-readonly-notice")).toBeNull();
    await act(async () => {
      useWorkspaceStore.getState().initialise("u1", "t1", stored(memberships));
      useWorkspaceStore.getState().setActive("t9");
    });
    expect(await screen.findByTestId("models-readonly-notice")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByTestId(/^provider-row-/)).toHaveLength(1));
    expect(callsTo("/api/v1/providers").map(tenantOf)).toEqual(expect.arrayContaining(["t1", "t9"]));
  });
});

describe("States", () => {
  it("shows skeleton rows with an announced status while the providers load", async () => {
    let release: () => void = () => undefined;
    hold = new Promise<void>((resolve) => (release = resolve));
    renderPage();
    expect(screen.getByTestId("providers-skeleton")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading model providers");
    await act(async () => release());
    expect(await screen.findByTestId("provider-row-openai")).toBeInTheDocument();
    expect(screen.queryByTestId("providers-skeleton")).toBeNull();
  });

  it("fails in place with the noun 'model providers' and recovers with Try again", async () => {
    forced["GET /api/v1/providers"] = { status: 500, message: "boom" };
    renderPage();
    const state = await screen.findByTestId("error-state");
    expect(within(state).getByRole("heading", { name: "Couldn't load model providers" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Models" })).toBeInTheDocument();
    delete forced["GET /api/v1/providers"];
    await userEvent.setup().click(within(state).getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("provider-row-openai")).toBeInTheDocument();
    expect(screen.queryByTestId("error-state")).toBeNull();
  });

  it("keeps the provider rows when only the defaults request fails, just without default badges", async () => {
    forced["GET /api/v1/models/default"] = { status: 500, message: "boom" };
    renderPage();
    await screen.findByTestId("provider-row-openai");
    await waitFor(() => expect(within(rowOf("openrouter")).getAllByTestId("model-row")).toHaveLength(2));
    expect(screen.queryByTestId("error-state")).toBeNull();
    expect(screen.queryByText("Default embedding")).toBeNull();
  });
});
