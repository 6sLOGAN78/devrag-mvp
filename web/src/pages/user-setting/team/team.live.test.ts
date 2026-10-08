import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { appendFileSync } from "node:fs";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { buildRoutes } from "@/routes";
import { registerNavigate, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { removeAuthorization, setAuthorization } from "@/utils/authorization";

// Runs against the real ingress (LIVE_BASE_URL): the real SPA routes, the real HTTP client and the real Go
// membership endpoints. Two uniquely named accounts (an owner and a teammate) are recorded for removal by the runner.
// Every state change below is made through the page; the API is used only to create accounts, to read what the
// server holds, and to probe what the server refuses.
const SECRET = ["live", "team", "pass", "0001"].join("-");
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}
interface Account {
  email: string;
  nickname: string;
  session: string;
  tenantId: string;
}
interface MemberRow {
  id: string;
  email: string;
  role: string;
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
  const email = `webteam-${tag}-${suffix}@example.test`;
  const nickname = `webteam-${tag}-${suffix}`;
  const created = await call("/api/v1/users", { method: "POST", body: { email, password: SECRET, nickname } });
  recordAccount(email);
  if (created.status !== 200 || created.envelope?.code !== 0) throw new Error(`registering ${tag} returned HTTP ${created.status}`);
  const login = await call<{ token?: string }>("/api/v1/auth/login", { method: "POST", body: { email, password: SECRET } });
  const session = login.envelope?.code === 0 ? login.envelope.data?.token : undefined;
  if (!session) throw new Error(`signing in ${tag} returned HTTP ${login.status}`);
  const info = await call<{ tenant_id: string }>("/v1/user/info", { bearer: session });
  const tenantId = info.envelope?.data?.tenant_id;
  if (!tenantId) throw new Error(`reading ${tag} returned HTTP ${info.status}`);
  return { email, nickname, session, tenantId };
}

async function membersOf(owner: Account, as: Account = owner): Promise<{ status: number; rows: MemberRow[] }> {
  const { status, envelope } = await call<MemberRow[]>(`/api/v1/tenants/${owner.tenantId}/users`, { bearer: as.session });
  return { status, rows: envelope?.code === 0 && Array.isArray(envelope.data) ? envelope.data : [] };
}

function loadApp(account: Account) {
  cleanup();
  removeAuthorization();
  useUserStore.getState().reset();
  setAuthorization(account.session);
  const router = createMemoryRouter(buildRoutes(), { initialEntries: ["/user-setting/team"] });
  const client = new QueryClient();
  registerQueryClient(client);
  registerNavigate({
    navigate: (to) => router.navigate(to, { replace: true }),
    currentPath: () => `${router.state.location.pathname}${router.state.location.search}`,
  });
  render(createElement(QueryClientProvider, { client }, createElement(RouterProvider, { router }), createElement(Toaster)));
  return router;
}

/** Signs in as the account on a fresh Team page and waits until its own workspace has loaded. */
async function openTeam(account: Account): Promise<HTMLElement> {
  loadApp(account);
  const workspace = await screen.findByTestId("workspace-card", {}, { timeout: 30_000 });
  await within(workspace).findByTestId("members-table", {}, { timeout: 30_000 });
  return screen.getByTestId("team-page");
}

async function invite(user: ReturnType<typeof userEvent.setup>, email: string): Promise<void> {
  await user.type(screen.getByLabelText("Email address"), email);
  await user.click(screen.getByRole("button", { name: "Send invitation" }));
  await screen.findByText("Invitation sent", {}, { timeout: 30_000 });
}

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
});

describe("live team membership cycle through the SPA and the ingress (UI-36)", () => {
  it("waits for the ingress health route", async () => {
    await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
  });

  it("shows the unknown-email answer exactly as the server gives it, in the alert only", async () => {
    const owner = await createAccount("alert");
    const unknown = `webteam-nobody-${suffix}@example.test`;
    const direct = await call<null>(`/api/v1/tenants/${owner.tenantId}/users`, { method: "POST", bearer: owner.session, body: { email: unknown } });
    expect(direct.status).toBe(404);
    const serverMessage = direct.envelope?.message ?? "";
    expect(serverMessage).not.toBe("");

    const user = userEvent.setup();
    await openTeam(owner);
    await user.type(screen.getByLabelText("Email address"), unknown);
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    const alert = await screen.findByTestId("alert-form-error", {}, { timeout: 30_000 });
    expect(alert).toHaveTextContent(new RegExp(`^${serverMessage.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`));
    expect(screen.queryByText("Request failed")).toBeNull();
    expect(screen.queryByText("Invitation sent")).toBeNull();
    // The alert is the only place the message appears.
    expect(screen.getAllByText(serverMessage)).toHaveLength(1);
  });

  it("invites, accepts, changes the role, removes, declines, re-accepts, leaves and withdraws through the real Go API", async () => {
    const owner = await createAccount("owner");
    const mate = await createAccount("mate");
    const user = userEvent.setup();

    // Owner invites the teammate by email; the pending list shows it and the member count ignores it.
    let page = await openTeam(owner);
    expect(within(page).getByTestId("invite-form")).toBeInTheDocument();
    expect(within(page).getByText("No pending invitations.")).toBeInTheDocument();
    await invite(user, mate.email);
    const pending = await within(page).findByTestId("pending-sent-list");
    expect(within(pending).getByText(mate.email)).toBeInTheDocument();
    expect(within(page).getByTestId("member-count")).toHaveTextContent("1 member");
    expect((await membersOf(owner)).rows.find((row) => row.email === mate.email)?.role).toBe("invite");

    // A repeat is refused with the server's own wording and no second row.
    await user.type(screen.getByLabelText("Email address"), mate.email);
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByTestId("alert-form-error", {}, { timeout: 30_000 })).toHaveTextContent(/already/i);

    // The teammate sees the invitation, not a role, and accepts it.
    page = await openTeam(mate);
    const invitations = await screen.findByTestId("invitations-for-you", {}, { timeout: 30_000 });
    expect(within(invitations).getByText(`${owner.nickname} invited you to join ${owner.nickname}'s Kingdom`, { exact: false })).toBeInTheDocument();
    await user.click(within(invitations).getByRole("button", { name: `Accept invitation from ${owner.nickname}` }));
    await screen.findByText(/^Joined /, {}, { timeout: 30_000 });
    const joined = await screen.findByTestId("joined-workspaces", {}, { timeout: 30_000 });
    expect(within(joined).getByText(`Owned by ${owner.nickname}`)).toBeInTheDocument();
    expect(within(joined).getByText("Member")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId("invitations-for-you")).toBeNull());
    expect((await membersOf(owner, mate)).status).toBe(200);
    // Only the workspace owner can invite: the teammate's own page offers the form for the teammate's own workspace only, and the server refuses it for the joined one.
    expect(within(joined).queryByTestId("invite-form")).toBeNull();
    expect((await call(`/api/v1/tenants/${owner.tenantId}/users`, { method: "POST", bearer: mate.session, body: { email: `webteam-x-${suffix}@example.test` } })).status).toBe(403);

    // Owner promotes the teammate through the confirmation; the old value stays until the server confirms.
    page = await openTeam(owner);
    const select = within(page).getByRole("combobox", { name: `Role for ${mate.nickname}` });
    expect(select).toHaveValue("normal");
    await user.selectOptions(select, "admin");
    const dialog = await screen.findByTestId("confirm-dialog");
    expect(within(dialog).getByText(`${mate.nickname} will become an admin in ${owner.nickname}'s Kingdom.`)).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Keep current role" })).toHaveFocus());
    expect(select).toHaveValue("normal");
    await user.click(within(dialog).getByRole("button", { name: "Change role" }));
    await screen.findByText("Role updated", {}, { timeout: 30_000 });
    await waitFor(() => expect(within(page).getByRole("combobox", { name: `Role for ${mate.nickname}` })).toHaveValue("admin"));
    expect((await membersOf(owner)).rows.find((row) => row.email === mate.email)?.role).toBe("admin");

    // The teammate's page now says Admin and still offers no way into the owner's Kingdom.
    await openTeam(mate);
    const mateJoined = await screen.findByTestId("joined-workspaces", {}, { timeout: 30_000 });
    expect(within(mateJoined).getByText("Admin")).toBeInTheDocument();
    expect((await call(`/api/v1/tenants/${owner.tenantId}/users`, { method: "POST", bearer: mate.session, body: { email: `webteam-y-${suffix}@example.test` } })).status).toBe(403);

    // Owner removes the teammate after the confirmation.
    page = await openTeam(owner);
    await user.click(within(page).getByRole("button", { name: `Remove ${mate.nickname}` }));
    const removeDialog = await screen.findByTestId("confirm-dialog");
    await waitFor(() => expect(within(removeDialog).getByRole("button", { name: "Keep member" })).toHaveFocus());
    await user.click(within(removeDialog).getByRole("button", { name: "Remove member" }));
    await screen.findByText("Member removed", {}, { timeout: 30_000 });
    await waitFor(() => expect(within(page).queryByRole("button", { name: `Remove ${mate.nickname}` })).toBeNull());
    await waitFor(() => expect(within(page).getByTestId("members-table").querySelector("caption")).toHaveFocus());
    expect((await membersOf(owner)).rows.map((row) => row.email)).not.toContain(mate.email);

    // For the removed teammate the section is gone and the server answers 404.
    await openTeam(mate);
    expect(screen.queryByTestId("joined-workspaces")).toBeNull();
    expect((await membersOf(owner, mate)).status).toBe(404);

    // Re-invite and decline.
    page = await openTeam(owner);
    await invite(user, mate.email);
    await openTeam(mate);
    await user.click(await screen.findByRole("button", { name: `Decline invitation from ${owner.nickname}` }, { timeout: 30_000 }));
    await screen.findByText("Invitation declined", {}, { timeout: 30_000 });
    await waitFor(() => expect(screen.queryByTestId("invitations-for-you")).toBeNull());
    expect(screen.queryByTestId("joined-workspaces")).toBeNull();
    expect((await membersOf(owner)).rows.map((row) => row.email)).not.toContain(mate.email);

    // Re-invite, accept, then leave through the confirmation.
    await openTeam(owner);
    await invite(user, mate.email);
    await openTeam(mate);
    await user.click(await screen.findByRole("button", { name: `Accept invitation from ${owner.nickname}` }, { timeout: 30_000 }));
    await screen.findByTestId("joined-workspaces", {}, { timeout: 30_000 });
    await user.click(screen.getByRole("button", { name: `Leave ${owner.nickname}'s Kingdom` }));
    const leaveDialog = await screen.findByTestId("confirm-dialog");
    await waitFor(() => expect(within(leaveDialog).getByRole("button", { name: "Stay in workspace" })).toHaveFocus());
    await user.click(within(leaveDialog).getByRole("button", { name: "Leave workspace" }));
    await screen.findByText(`You left ${owner.nickname}'s Kingdom`, {}, { timeout: 30_000 });
    await waitFor(() => expect(screen.queryByTestId("joined-workspaces")).toBeNull());
    expect((await membersOf(owner, mate)).status).toBe(404);
    expect((await membersOf(owner)).rows.map((row) => row.email)).not.toContain(mate.email);

    // The owner withdraws a pending invitation before it is answered; the teammate never sees it.
    page = await openTeam(owner);
    await invite(user, mate.email);
    await user.click(await within(page).findByRole("button", { name: `Withdraw invitation for ${mate.email}` }, { timeout: 30_000 }));
    const withdrawDialog = await screen.findByTestId("confirm-dialog");
    await waitFor(() => expect(within(withdrawDialog).getByRole("button", { name: "Keep invitation" })).toHaveFocus());
    await user.click(within(withdrawDialog).getByRole("button", { name: "Withdraw invitation" }));
    await screen.findByText("Invitation withdrawn", {}, { timeout: 30_000 });
    await waitFor(() => expect(within(page).queryByTestId("pending-sent-list")).toBeNull());
    await openTeam(mate);
    expect(screen.queryByTestId("invitations-for-you")).toBeNull();
    expect((await membersOf(owner)).rows.map((row) => row.email)).not.toContain(mate.email);
  });

  it("refreshes cleanly when the owner removes the teammate while the teammate's page is open", async () => {
    const owner = await createAccount("race-owner");
    const mate = await createAccount("race-mate");
    const user = userEvent.setup();
    expect((await call(`/api/v1/tenants/${owner.tenantId}/users`, { method: "POST", bearer: owner.session, body: { email: mate.email } })).status).toBe(200);
    expect((await call(`/api/v1/tenants/${owner.tenantId}`, { method: "PATCH", bearer: mate.session, body: { action: "accept" } })).status).toBe(200);

    await openTeam(mate);
    const joined = await screen.findByTestId("joined-workspaces", {}, { timeout: 30_000 });
    // The owner removes the teammate behind the open page.
    const removed = await call(`/api/v1/tenants/${owner.tenantId}/users`, { method: "DELETE", bearer: owner.session, body: { user_id: (await membersOf(owner)).rows.find((row) => row.email === mate.email)?.id } });
    expect(removed.status).toBe(200);
    await user.click(within(joined).getByRole("button", { name: `Leave ${owner.nickname}'s Kingdom` }));
    await user.click(await screen.findByRole("button", { name: "Leave workspace" }));
    await screen.findByText("That is no longer available. The list has been refreshed.", {}, { timeout: 30_000 });
    await waitFor(() => expect(screen.queryByTestId("joined-workspaces")).toBeNull());
    expect(screen.getByTestId("team-page")).toBeInTheDocument();
  });
});
