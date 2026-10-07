import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { appendFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { buildRoutes } from "@/routes";
import { registerNavigate, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { removeAuthorization, setAuthorization } from "@/utils/authorization";
import { maskToken } from "./mask";

// Runs against the real ingress (LIVE_BASE_URL): the real SPA routes, the real HTTP client and the real Go token
// endpoints. Each account is its own, uniquely named, and recorded for removal by the runner (which also removes the
// api_token rows of those accounts). The probe path technique: a request to an unregistered /api/v1/probe-<uuid>
// path is 404 once the gate accepts the credential and 401 when it refuses it, so it observes a token's validity
// without needing any feature endpoint.
const SECRET = ["live", "token", "pass", "0001"].join("-");
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}
interface Account {
  email: string;
  session: string;
}

function recordAccount(email: string): void {
  const file = process.env.LIVE_ACCOUNTS_FILE;
  if (file) appendFileSync(file, `${email}\n`);
}

async function call<T>(path: string, init: { method?: string; bearer?: string; body?: unknown } = {}): Promise<{ status: number; envelope: Envelope<T> | null }> {
  const response = await fetch(new URL(path, window.location.origin), {
    method: init.method ?? "GET",
    headers: { "Content-Type": "application/json", ...(init.bearer ? { Authorization: `Bearer ${init.bearer}` } : {}) },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  let envelope: Envelope<T> | null = null;
  try {
    envelope = (await response.json()) as Envelope<T>;
  } catch {
    envelope = null;
  }
  return { status: response.status, envelope };
}

async function createAccount(tag: string): Promise<Account> {
  const email = `webtokens-${tag}-${suffix}@example.test`;
  const created = await call("/api/v1/users", { method: "POST", body: { email, password: SECRET, nickname: `webtokens-${tag}-${suffix}` } });
  recordAccount(email);
  if (created.status !== 200 || created.envelope?.code !== 0) throw new Error(`registering ${tag} returned HTTP ${created.status}`);
  const login = await call<{ token?: string }>("/api/v1/auth/login", { method: "POST", body: { email, password: SECRET } });
  const session = login.envelope?.code === 0 ? login.envelope.data?.token : undefined;
  if (!session) throw new Error(`signing in ${tag} returned HTTP ${login.status}`);
  return { email, session };
}

/** Status of a request that carries only the given API token. 404 = the gate accepted it, 401 = refused. */
async function probe(apiToken: string): Promise<number> {
  return (await call(`/api/v1/probe-${randomUUID()}`, { bearer: apiToken })).status;
}

async function listTokens(session: string): Promise<{ token: string }[]> {
  const { envelope } = await call<{ token: string }[]>("/api/v1/system/tokens", { bearer: session });
  if (!envelope || envelope.code !== 0) throw new Error("GET /api/v1/system/tokens failed");
  return envelope.data;
}

function loadApp(path: string) {
  useUserStore.getState().reset();
  const router = createMemoryRouter(buildRoutes(), { initialEntries: [path] });
  const client = new QueryClient();
  registerQueryClient(client);
  registerNavigate({
    navigate: (to) => router.navigate(to, { replace: true }),
    currentPath: () => `${router.state.location.pathname}${router.state.location.search}`,
  });
  render(createElement(QueryClientProvider, { client }, createElement(RouterProvider, { router }), createElement(Toaster)));
  return router;
}

const writeText = vi.fn();

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});
afterEach(() => {
  cleanup();
  registerNavigate(null);
  removeAuthorization();
  useUserStore.getState().reset();
  vi.restoreAllMocks();
  writeText.mockReset();
});

function stubClipboard(): void {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: (text: string) => Promise.resolve(void writeText(text)) } });
}

describe("live API token lifecycle through the SPA and the ingress (UI-35)", () => {
  it("waits for the ingress health route", async () => {
    await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
  });

  it("redirects a signed-out visit of /user-setting/api to /login with the encoded next", async () => {
    localStorage.clear();
    const router = loadApp("/user-setting/api");
    await waitUntil(() => router.state.location.pathname === "/login", { describe: "the guard redirect" });
    expect(router.state.location.search).toBe("?next=%2Fuser-setting%2Fapi");
    expect(screen.queryByTestId("tokens-page")).toBeNull();
  });

  it("creates, lists masked, reveals, copies and deletes a token; the deleted token then gets 401", async () => {
    const account = await createAccount("lifecycle");
    setAuthorization(account.session);
    const user = userEvent.setup();
    stubClipboard();
    loadApp("/user-setting/api");

    await screen.findByRole("heading", { level: 2, name: "No API tokens yet" }, { timeout: 30_000 });
    await user.click(screen.getByRole("button", { name: "Create token" }));
    const dialog = await screen.findByTestId("token-created-dialog", {}, { timeout: 30_000 });
    const apiToken = (within(dialog).getByLabelText("API token") as HTMLInputElement).value;
    expect(apiToken).toMatch(/^ragflow-[A-Za-z0-9_-]{16,}$/);
    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    await waitUntil(() => screen.queryByTestId("token-created-dialog") === null, { describe: "the created dialog closing" });

    // Listed masked: the full value is neither in the DOM nor in storage.
    const cell = await waitUntil(() => screen.queryByTestId("token-value"), { describe: "the new row" });
    expect(cell.textContent).toBe(maskToken(apiToken));
    expect(document.body.innerHTML).not.toContain(apiToken);
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(apiToken);
    expect((await listTokens(account.session)).map((t) => t.token)).toEqual([apiToken]);

    // The token works on its own: the gate passes it (404 for an unregistered path, not 401).
    expect(await probe(apiToken)).toBe(404);

    // Reveal shows the full value; copy writes it while masked.
    const tail = apiToken.slice(-4);
    await user.click(screen.getByRole("button", { name: `Show token ending ${tail}` }));
    expect(screen.getByTestId("token-value")).toHaveTextContent(apiToken);
    await user.click(screen.getByRole("button", { name: `Hide token ending ${tail}` }));
    expect(screen.getByTestId("token-value").textContent).toBe(maskToken(apiToken));
    await user.click(screen.getByRole("button", { name: `Copy token ending ${tail}` }));
    expect(writeText).toHaveBeenCalledExactlyOnceWith(apiToken);

    // Delete: keep first (nothing changes), then confirm.
    await user.click(screen.getByRole("button", { name: `Delete token ending ${tail}` }));
    await user.click(await screen.findByRole("button", { name: "Keep token" }));
    await waitUntil(() => screen.queryByTestId("token-delete-dialog") === null, { describe: "the delete dialog closing" });
    expect(await probe(apiToken)).toBe(404);
    await user.click(screen.getByRole("button", { name: `Delete token ending ${tail}` }));
    await user.click(await screen.findByRole("button", { name: "Delete token" }));
    await screen.findByText("Token deleted");
    await screen.findByRole("heading", { level: 2, name: "No API tokens yet" });

    expect(await probe(apiToken)).toBe(401);
    expect(await listTokens(account.session)).toEqual([]);
  });

  it("does not let another account's session delete a token: 404 and the token keeps working", async () => {
    const owner = await createAccount("owner");
    const other = await createAccount("other");
    const created = await call<{ token: string }>("/api/v1/system/tokens", { method: "POST", bearer: owner.session });
    expect(created.status).toBe(200);
    const apiToken = created.envelope!.data.token;

    const foreign = await call(`/api/v1/system/tokens/${encodeURIComponent(apiToken)}`, { method: "DELETE", bearer: other.session });
    expect(foreign.status).toBe(404);
    expect(await probe(apiToken)).toBe(404);
    expect((await listTokens(other.session)).map((t) => t.token)).not.toContain(apiToken);

    // The owner's page refreshes cleanly when the token disappears elsewhere (404 on delete).
    setAuthorization(owner.session);
    const user = userEvent.setup();
    loadApp("/user-setting/api");
    const tail = apiToken.slice(-4);
    await user.click(await screen.findByRole("button", { name: `Delete token ending ${tail}` }, { timeout: 30_000 }));
    const removed = await call(`/api/v1/system/tokens/${encodeURIComponent(apiToken)}`, { method: "DELETE", bearer: owner.session });
    expect(removed.status).toBe(200);
    await user.click(await screen.findByRole("button", { name: "Delete token" }));
    await screen.findByRole("heading", { level: 2, name: "No API tokens yet" });
    expect(screen.queryByText(/not found/i)).toBeNull();
    expect(await probe(apiToken)).toBe(401);
  });
});
