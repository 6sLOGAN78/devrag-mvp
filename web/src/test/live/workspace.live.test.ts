import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { appendFileSync } from "node:fs";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { MEMBERSHIPS_QUERY_KEY } from "@/hooks/use-team-request";
import { buildRoutes } from "@/routes";
import { registerNavigate, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { waitUntil } from "@/test/wait-until";
import { removeAuthorization, setAuthorization } from "@/utils/authorization";

// Runs against the real ingress (LIVE_BASE_URL): the real SPA routes and header, the real HTTP client and the real Go
// membership endpoints. Three uniquely named accounts: an owner (A), a teammate who joins A's workspace (B) and a
// user who belongs to nobody else's workspace (C). Accounts and memberships are made through the real API; the
// workspace menu itself is driven through the rendered header.
const SECRET = ["live", "workspace", "pass", "0001"].join("-");
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
const STORAGE_KEY = "devrag.workspace";

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}
interface Account {
  email: string;
  session: string;
  userId: string;
  tenantId: string;
  tenantName: string;
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
  const email = `webws-${tag}-${suffix}@example.test`;
  const created = await call("/api/v1/users", { method: "POST", body: { email, password: SECRET, nickname: `webws-${tag}-${suffix}` } });
  recordAccount(email);
  if (created.status !== 200 || created.envelope?.code !== 0) throw new Error(`registering ${tag} returned HTTP ${created.status}`);
  const login = await call<{ token?: string }>("/api/v1/auth/login", { method: "POST", body: { email, password: SECRET } });
  const session = login.envelope?.code === 0 ? login.envelope.data?.token : undefined;
  if (!session) throw new Error(`signing in ${tag} returned HTTP ${login.status}`);
  const info = await call<{ id: string; tenant_id: string; tenant_name: string }>("/v1/user/info", { bearer: session });
  const data = info.envelope?.data;
  if (!data?.tenant_id || !data.id) throw new Error(`reading ${tag} returned HTTP ${info.status}`);
  return { email, session, userId: data.id, tenantId: data.tenant_id, tenantName: data.tenant_name };
}

async function join(owner: Account, mate: Account): Promise<void> {
  const invited = await call(`/api/v1/tenants/${owner.tenantId}/users`, { method: "POST", bearer: owner.session, body: { email: mate.email } });
  expect(invited.status).toBe(200);
  const accepted = await call(`/api/v1/tenants/${owner.tenantId}`, { method: "PATCH", bearer: mate.session, body: { action: "accept" } });
  expect(accepted.status).toBe(200);
}

/** A page reload: the in-memory workspace state is gone, the stored choice stays. */
function forgetInMemoryWorkspaceState(): void {
  useWorkspaceStore.setState({ activeTenantId: null, initialisedFor: null, ownTenantId: null, memberships: [], lost: null });
}

/** Mounts the real app shell signed in as the account and waits until its membership list has been answered. */
async function loadApp(account: Account): Promise<QueryClient> {
  cleanup();
  removeAuthorization();
  useUserStore.getState().reset();
  forgetInMemoryWorkspaceState();
  setAuthorization(account.session);
  const router = createMemoryRouter(buildRoutes(), { initialEntries: ["/home"] });
  const client = new QueryClient();
  registerQueryClient(client);
  registerNavigate({
    navigate: (to) => router.navigate(to, { replace: true }),
    currentPath: () => `${router.state.location.pathname}${router.state.location.search}`,
  });
  render(createElement(QueryClientProvider, { client }, createElement(RouterProvider, { router }), createElement(Toaster)));
  await screen.findByRole("banner", {}, { timeout: 30_000 });
  await waitUntil(() => client.getQueryState(MEMBERSHIPS_QUERY_KEY)?.status === "success" && client.isFetching() === 0, {
    describe: "the membership list to load",
    timeout: 30_000,
  });
  await waitUntil(() => useWorkspaceStore.getState().initialisedFor === account.userId, { describe: "the workspace store to initialise", timeout: 30_000 });
  return client;
}

const storedChoice = (): unknown => JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");

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
  useWorkspaceStore.getState().reset();
});

describe("live workspace selector through the SPA and the ingress (D-26, TEN-13)", () => {
  it("waits for the ingress health route", async () => {
    await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
  });

  it("lists own then joined workspaces, switches, persists the choice and restores it after a reload", async () => {
    const owner = await createAccount("owner");
    const mate = await createAccount("mate");
    await join(owner, mate);
    const user = userEvent.setup();

    await loadApp(mate);
    const header = screen.getByRole("banner");
    const trigger = await within(header).findByRole("button", { name: `Workspace: ${mate.tenantName}. Change workspace` }, { timeout: 30_000 });
    expect(trigger).toHaveAttribute("data-testid", "workspace-switch");

    await user.click(trigger);
    const menu = await screen.findByRole("menu");
    const options = within(menu).getAllByRole("menuitemradio");
    expect(options.map((o) => o.getAttribute("data-testid"))).toEqual([`workspace-option-${mate.tenantId}`, `workspace-option-${owner.tenantId}`]);
    expect(options.map((o) => o.getAttribute("aria-checked"))).toEqual(["true", "false"]);
    expect(options[0]).toHaveTextContent(mate.tenantName);
    expect(options[1]).toHaveTextContent(owner.tenantName);
    expect(options[1]).toHaveTextContent("Member · Owned by");
    expect(within(menu).getByRole("menuitem", { name: "Manage team" })).toHaveAttribute("href", "/user-setting/team");

    // Switching to the owner's workspace stores the member's id and the owner's tenant id.
    await user.click(options[1]!);
    await within(header).findByRole("button", { name: `Workspace: ${owner.tenantName}. Change workspace` });
    expect(useWorkspaceStore.getState().activeTenantId).toBe(owner.tenantId);
    expect(storedChoice()).toEqual({ userId: mate.userId, tenantId: owner.tenantId });
    expect(screen.getByTestId("workspace-announcer")).toHaveTextContent(`Switched to ${owner.tenantName}`);
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();

    // A fresh render restores the owner's workspace from storage, validated against the server list.
    await loadApp(mate);
    await screen.findByRole("button", { name: `Workspace: ${owner.tenantName}. Change workspace` }, { timeout: 30_000 });
    expect(useWorkspaceStore.getState().activeTenantId).toBe(owner.tenantId);
  });

  it("falls back to the own workspace once the owner removes the member", async () => {
    const owner = await createAccount("owner2");
    const mate = await createAccount("mate2");
    await join(owner, mate);

    await loadApp(mate);
    await screen.findByRole("button", { name: `Workspace: ${mate.tenantName}. Change workspace` }, { timeout: 30_000 });
    useWorkspaceStore.getState().setActive(owner.tenantId);
    expect(storedChoice()).toEqual({ userId: mate.userId, tenantId: owner.tenantId });

    const removed = await call(`/api/v1/tenants/${owner.tenantId}/users`, { method: "DELETE", bearer: owner.session, body: { user_id: mate.userId } });
    expect(removed.status).toBe(200);

    // The stored id is not in the server list any more: ignored, so the member lands in their own workspace.
    await loadApp(mate);
    expect(useWorkspaceStore.getState().activeTenantId).toBe(mate.tenantId);
    const current = await screen.findByTestId("workspace-current");
    expect(current).toHaveTextContent(mate.tenantName);
    expect(screen.queryByTestId("workspace-switch")).toBeNull();
  });

  it("shows plain text and no menu for a user with only their own workspace", async () => {
    const solo = await createAccount("solo");
    await loadApp(solo);
    const current = await screen.findByTestId("workspace-current", {}, { timeout: 30_000 });
    expect(current).toHaveTextContent(`Workspace:${solo.tenantName}`);
    expect(within(screen.getByRole("banner")).queryByTestId("workspace-switch")).toBeNull();
    expect(within(current).queryByRole("button")).toBeNull();
  });
});
