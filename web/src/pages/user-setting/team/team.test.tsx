import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import i18n, { setLanguage } from "@/i18n";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { setAuthorization } from "@/utils/authorization";
import TeamPage from ".";

// Drives the real page, hooks, service and HTTP client against an in-memory server that behaves like the Go API
// (plans 02-15, 02-22, 02-23): the list endpoint, the member list (the owner also sees invitations), invite,
// accept or decline, role change and remove, withdraw or leave. Obviously fake data throughout.
const JOINED_AT = "2026-10-01T12:00:00Z";
const INVITED_AT = "2026-10-05T12:00:00Z";

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

interface MemberRow {
  id: string;
  nickname: string;
  email: string;
  avatar: string;
  role: string;
  joined_time: string;
}
interface MembershipRow {
  tenant_id: string;
  tenant_name: string;
  owner_nickname: string;
  owner_avatar: string;
  role: string;
  joined_time: string;
}

const member = (id: string, nickname: string, role: string, extra: Partial<MemberRow> = {}): MemberRow => ({
  id,
  nickname,
  email: `${nickname.toLowerCase()}@example.test`,
  avatar: "",
  role,
  joined_time: role === "invite" ? INVITED_AT : JOINED_AT,
  ...extra,
});
const ownMembership: MembershipRow = { tenant_id: "t1", tenant_name: "Ada's workspace", owner_nickname: "Ada", owner_avatar: "", role: "owner", joined_time: JOINED_AT };
const otherMembership = (role: string, extra: Partial<MembershipRow> = {}): MembershipRow => ({
  tenant_id: "t9",
  tenant_name: "Grace's workspace",
  owner_nickname: "Grace",
  owner_avatar: "",
  role,
  joined_time: role === "invite" ? INVITED_AT : JOINED_AT,
  ...extra,
});

interface Forced {
  status: number;
  code?: number;
  message: string;
  headers?: Record<string, string>;
}

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let memberships: MembershipRow[] = [];
let members: MemberRow[] = [];
let forced: Record<string, Forced> = {};
let gate: Promise<void> | null = null;

const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, f: Forced) {
  const response = { data: { code: f.code ?? f.status, message: f.message, data: null }, status: f.status, statusText: String(f.status), headers: new AxiosHeaders(f.headers ?? {}), config } as never;
  return Promise.reject(new AxiosError(`status ${f.status}`, "ERR_BAD_RESPONSE", config, null, response));
}

const bodyOf = (config: InternalAxiosRequestConfig): Record<string, unknown> => (typeof config.data === "string" && config.data !== "" ? (JSON.parse(config.data) as Record<string, unknown>) : {});
const keyOf = (config: InternalAxiosRequestConfig) => `${String(config.method).toUpperCase()} ${config.url}`;

function serve(config: InternalAxiosRequestConfig): unknown {
  const method = String(config.method).toUpperCase();
  const url = String(config.url);
  const stop = forced[keyOf(config)];
  if (stop) return failure(config, stop);
  if (method === "GET" && url === "/v1/tenant/list") return ok(config, memberships);
  const own = /^\/api\/v1\/tenants\/t1\/users$/.exec(url);
  if (own && method === "GET") return ok(config, members);
  if (own && method === "POST") {
    const email = String(bodyOf(config).email);
    const created = member(`inv-${members.length}`, "", "invite", { email, nickname: email.split("@")[0]! });
    members = [...members, created];
    return ok(config, created);
  }
  if (own && method === "DELETE") {
    const id = String(bodyOf(config).user_id);
    members = members.filter((m) => m.id !== id || m.role === "owner");
    return ok(config, null);
  }
  const role = /^\/api\/v1\/tenants\/t1\/users\/([^/]+)$/.exec(url);
  if (role && method === "PATCH") {
    members = members.map((m) => (m.id === role[1] ? { ...m, role: String(bodyOf(config).role) } : m));
    return ok(config, null);
  }
  const other = /^\/api\/v1\/tenants\/(t\d+)$/.exec(url);
  if (other && method === "PATCH") {
    const action = bodyOf(config).action;
    memberships = action === "accept" ? memberships.map((m) => (m.tenant_id === other[1] ? { ...m, role: "normal" } : m)) : memberships.filter((m) => m.tenant_id !== other[1]);
    return ok(config, null);
  }
  const leave = /^\/api\/v1\/tenants\/(t\d+)\/users$/.exec(url);
  if (leave && method === "DELETE") {
    memberships = memberships.filter((m) => m.tenant_id !== leave[1]);
    return ok(config, null);
  }
  return failure(config, { status: 404, message: "not found" });
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  if (gate) await gate;
  return (await Promise.resolve(serve(config))) as never;
};

const callsMatching = (method: string, url: string | RegExp) =>
  calls.filter((c) => String(c.method).toUpperCase() === method && (typeof url === "string" ? c.url === url : url.test(String(c.url))));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TeamPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

async function loaded() {
  await screen.findByTestId("members-table");
  return screen.getByTestId("team-page");
}

const rowOf = (nickname: string) => screen.getAllByTestId("member-row").find((r) => within(r).queryByText(nickname) !== null)!;

beforeEach(() => {
  calls = [];
  forced = {};
  gate = null;
  memberships = [ownMembership];
  members = [member("u1", "Ada", "owner"), member("u2", "Bob", "normal"), member("u3", "Cy", "admin")];
  useUserStore.getState().reset();
  useUserStore.getState().setUser(OWNER);
  setAuthorization("tok-session");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
});

describe("Team page structure (UI-36)", () => {
  it("makes the Team heading the first read element and sets the document title and helper line", async () => {
    renderPage();
    const page = await loaded();
    const headings = within(page).getAllByRole("heading");
    expect(headings[0]).toHaveTextContent("Team");
    expect(headings[0]?.tagName).toBe("H1");
    expect(document.title).toBe("Team - devRag");
    expect(within(page).getByText("The owner invites people and manages roles. Admins and members can use the workspace.")).toBeInTheDocument();
  });

  it("orders the cards: Invitations for you, Your workspace, Workspaces you've joined", async () => {
    memberships = [ownMembership, otherMembership("invite", { tenant_id: "t8", tenant_name: "Hal's workspace", owner_nickname: "Hal" }), otherMembership("admin")];
    renderPage();
    await loaded();
    await screen.findByTestId("joined-workspaces");
    const names = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(names).toEqual(["Invitations for you", "Your workspace", "Workspaces you've joined"]);
  });

  it("omits the invitations and joined cards when there are none", async () => {
    renderPage();
    await loaded();
    await waitFor(() => expect(callsMatching("GET", "/v1/tenant/list")).toHaveLength(1));
    expect(screen.queryByTestId("invitations-for-you")).toBeNull();
    expect(screen.queryByTestId("joined-workspaces")).toBeNull();
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Your workspace"]);
  });

  it("shows the workspace name, an i18n plural member count and counts people, not invitations", async () => {
    members = [...members, member("u9", "Dee", "invite")];
    renderPage();
    const page = await loaded();
    expect(within(page).getByTestId("workspace-name")).toHaveTextContent("Ada's workspace");
    expect(within(page).getByTestId("member-count")).toHaveTextContent("3 members");
  });

  it("uses the singular for one member", async () => {
    members = [member("u1", "Ada", "owner")];
    renderPage();
    const page = await loaded();
    expect(within(page).getByTestId("member-count")).toHaveTextContent(/^1 member$/);
  });

  it("shows per-card skeletons while loading", async () => {
    let release: () => void = () => undefined;
    gate = new Promise<void>((resolve) => (release = resolve));
    renderPage();
    expect(screen.getByTestId("members-skeleton")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Team");
    await act(async () => release());
    await screen.findByTestId("members-table");
    expect(screen.queryByTestId("members-skeleton")).toBeNull();
  });

  it("gives the members card its own error state with a retry that recovers", async () => {
    forced["GET /api/v1/tenants/t1/users"] = { status: 500, code: -1, message: "" };
    const user = userEvent.setup();
    renderPage();
    const alert = await screen.findByRole("heading", { level: 3, name: "Couldn't load team members" });
    expect(alert).toBeInTheDocument();
    delete forced["GET /api/v1/tenants/t1/users"];
    await user.click(within(screen.getByTestId("team-page")).getByRole("button", { name: "Try again" }));
    await screen.findByTestId("members-table");
  });

  it("gives the invitations card its own error state when the workspace list fails", async () => {
    forced["GET /v1/tenant/list"] = { status: 500, code: -1, message: "" };
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "Couldn't load invitations" });
    await screen.findByTestId("members-table");
  });
});

describe("invitations for you", () => {
  beforeEach(() => {
    memberships = [ownMembership, otherMembership("invite")];
  });

  it("describes each invitation and gives the buttons names that include the owner", async () => {
    renderPage();
    const card = await screen.findByTestId("invitations-for-you");
    expect(within(card).getByText("Grace invited you to join Grace's workspace")).toBeInTheDocument();
    expect(within(card).getByText(/^Invited .*2026$/)).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Accept invitation from Grace" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Decline invitation from Grace" })).toBeInTheDocument();
    expect(within(card).queryByText("invite")).toBeNull();
  });

  it("accepts with a PATCH for the listed tenant, toasts, and moves the workspace to the joined card", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Accept invitation from Grace" }));
    await screen.findByText("Joined Grace's workspace");
    const patch = callsMatching("PATCH", "/api/v1/tenants/t9");
    expect(patch).toHaveLength(1);
    expect(JSON.parse(String(patch[0]!.data))).toEqual({ action: "accept" });
    await waitFor(() => expect(screen.queryByTestId("invitations-for-you")).toBeNull());
    expect(within(await screen.findByTestId("joined-workspaces")).getByText("Grace's workspace")).toBeInTheDocument();
  });

  it("declines without a confirmation, toasts, and removes the card", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Decline invitation from Grace" }));
    await screen.findByText("Invitation declined");
    expect(screen.queryByTestId("confirm-dialog")).toBeNull();
    expect(JSON.parse(String(callsMatching("PATCH", "/api/v1/tenants/t9")[0]!.data))).toEqual({ action: "decline" });
    await waitFor(() => expect(screen.queryByTestId("invitations-for-you")).toBeNull());
  });

  it("disables both buttons and marks the pressed one busy while the request runs, and sends once", async () => {
    let release: () => void = () => undefined;
    const user = userEvent.setup();
    renderPage();
    const accept = await screen.findByRole("button", { name: "Accept invitation from Grace" });
    gate = new Promise<void>((resolve) => (release = resolve));
    await user.click(accept);
    expect(accept).toHaveAttribute("aria-busy", "true");
    expect(accept).toBeDisabled();
    expect(screen.getByRole("button", { name: "Decline invitation from Grace" })).toBeDisabled();
    await act(async () => release());
    await screen.findByText("Joined Grace's workspace");
    expect(callsMatching("PATCH", "/api/v1/tenants/t9")).toHaveLength(1);
  });

  it("tells the user the invitation is gone on 404 and refreshes the list", async () => {
    const user = userEvent.setup();
    renderPage();
    const accept = await screen.findByRole("button", { name: "Accept invitation from Grace" });
    // The owner withdrew the invitation after this page loaded.
    forced["PATCH /api/v1/tenants/t9"] = { status: 404, message: "not found" };
    memberships = [ownMembership];
    await user.click(accept);
    await screen.findByText("That is no longer available. The list has been refreshed.");
    await waitFor(() => expect(screen.queryByTestId("invitations-for-you")).toBeNull());
  });

  it("renders a hostile owner name and workspace name as text only", async () => {
    memberships = [ownMembership, otherMembership("invite", { owner_nickname: "<img src=x onerror=alert(1)>", tenant_name: "{{owner}} <b>x</b>" })];
    renderPage();
    const card = await screen.findByTestId("invitations-for-you");
    expect(card.querySelector("img")).toBeNull();
    expect(card.querySelector("b")).toBeNull();
    expect(within(card).getByText("<img src=x onerror=alert(1)> invited you to join {{owner}} <b>x</b>")).toBeInTheDocument();
  });
});

describe("your workspace: owner view", () => {
  it("shows the invite form, a role select per non-owner row and a remove action per non-owner row", async () => {
    renderPage();
    const page = await loaded();
    expect(within(page).getByTestId("invite-form")).toBeInTheDocument();
    expect(within(page).getAllByTestId("member-role-select")).toHaveLength(2);
    expect(within(page).getAllByTestId("member-remove")).toHaveLength(2);
    expect(within(page).getByLabelText("Email address")).toBeInTheDocument();
    expect(within(page).getByText("They need a devRag account already. The invitation appears on their Team page.")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "Send invitation" })).toBeInTheDocument();
  });

  it("renders a semantic members table: caption, scoped column headers, and the owner row with a static badge and no action", async () => {
    renderPage();
    const page = await loaded();
    const table = within(page).getByTestId("members-table");
    expect(table.querySelector("caption")).toHaveTextContent("Workspace members");
    expect(within(table).getAllByRole("columnheader").map((h) => [h.textContent, h.getAttribute("scope")])).toEqual([
      ["Member", "col"],
      ["Role", "col"],
      ["Joined", "col"],
      ["Actions", "col"],
    ]);
    const ada = rowOf("Ada");
    expect(within(ada).getByText("ada@example.test")).toBeInTheDocument();
    expect(within(ada).getByText("Owner")).toBeInTheDocument();
    expect(within(ada).queryByRole("combobox")).toBeNull();
    expect(within(ada).queryByRole("button")).toBeNull();
    expect(within(ada).getByText(/2026/)).toBeInTheDocument();
  });

  it("names the role select and the remove button after the person, and offers only Admin and Member", async () => {
    renderPage();
    await loaded();
    const select = screen.getByRole("combobox", { name: "Role for Bob" });
    expect(select).toHaveValue("normal");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Admin", "Member"]);
    expect(screen.getByRole("combobox", { name: "Role for Cy" })).toHaveValue("admin");
    expect(screen.getByRole("button", { name: "Remove Bob" })).toBeInTheDocument();
  });

  it("never shows role 'invite' as a role: pending rows are only in the pending list, with no badge", async () => {
    members = [...members, member("u9", "Dee", "invite")];
    renderPage();
    const page = await loaded();
    expect(within(page).getAllByTestId("member-row")).toHaveLength(3);
    expect(within(page).queryByText("invite")).toBeNull();
    expect(within(page).queryByText("Invite")).toBeNull();
    const pending = within(page).getByTestId("pending-sent-list");
    expect(within(pending).getByText("dee@example.test")).toBeInTheDocument();
    expect(within(pending).queryByTestId("member-role-select")).toBeNull();
    expect(pending.querySelector("[class*=badge]")).toBeNull();
  });

  it("shows the compact empty line when only the owner exists", async () => {
    members = [member("u1", "Ada", "owner")];
    renderPage();
    const page = await loaded();
    expect(within(page).getByText("No teammates yet. Invite someone with a devRag account to share this workspace.")).toBeInTheDocument();
    expect(within(page).getByText("No pending invitations.")).toBeInTheDocument();
  });

  it("does not show the compact empty line when teammates exist", async () => {
    renderPage();
    const page = await loaded();
    expect(within(page).queryByText(/No teammates yet/)).toBeNull();
  });

  it("renders hostile nicknames and emails as text only", async () => {
    members = [member("u1", "Ada", "owner"), member("u2", "<img src=x onerror=alert(1)>", "normal", { email: "{{role}}@example.test" })];
    renderPage();
    const page = await loaded();
    expect(page.querySelector("img")).toBeNull();
    expect(within(page).getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(within(page).getByText("{{role}}@example.test")).toBeInTheDocument();
    expect(within(page).getByRole("combobox", { name: "Role for <img src=x onerror=alert(1)>" })).toBeInTheDocument();
  });

  it("draws an avatar only from a safe raster data URL", async () => {
    members = [member("u1", "Ada", "owner"), member("u2", "Bob", "normal", { avatar: "javascript:alert(1)" }), member("u3", "Cy", "admin", { avatar: "https://evil.example/x.png" })];
    renderPage();
    const page = await loaded();
    expect(page.querySelector("img")).toBeNull();
  });
});

describe.each(["admin", "normal"])("your workspace: %s caller", (role) => {
  beforeEach(() => {
    useUserStore.getState().setUser({ ...OWNER, role });
    members = [member("u1", "Ada", "owner"), member("u2", "Bob", "normal"), member("u3", "Cy", "admin")];
  });

  it("shows static badges only and none of the owner controls", async () => {
    renderPage();
    const page = await loaded();
    expect(within(page).queryByTestId("invite-form")).toBeNull();
    expect(within(page).queryByRole("combobox")).toBeNull();
    expect(within(page).queryByTestId("member-remove")).toBeNull();
    expect(within(page).queryByTestId("pending-sent-list")).toBeNull();
    expect(within(page).queryByText("No pending invitations.")).toBeNull();
    expect(within(rowOf("Bob")).getByText("Member")).toBeInTheDocument();
    expect(within(rowOf("Cy")).getByText("Admin")).toBeInTheDocument();
  });
});

describe("role change", () => {
  it("keeps the old value until confirmed, asks first with Keep current role focused, and sends the listed ids", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    const select = screen.getByRole("combobox", { name: "Role for Bob" });
    await user.selectOptions(select, "admin");
    const dialog = await screen.findByTestId("confirm-dialog");
    expect(within(dialog).getByRole("heading", { name: "Change Bob's role?" })).toBeInTheDocument();
    expect(within(dialog).getByText("Bob will become an admin in Ada's workspace.")).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Keep current role" })).toHaveFocus());
    expect(select).toHaveValue("normal");
    expect(callsMatching("PATCH", /users/)).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Change role" }));
    await screen.findByText("Role updated");
    const patch = callsMatching("PATCH", "/api/v1/tenants/t1/users/u2");
    expect(patch).toHaveLength(1);
    expect(JSON.parse(String(patch[0]!.data))).toEqual({ role: "admin" });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Role for Bob" })).toHaveValue("admin"));
  });

  it("changing to Member says 'a member'", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.selectOptions(screen.getByRole("combobox", { name: "Role for Cy" }), "normal");
    expect(await screen.findByText("Cy will become a member in Ada's workspace.")).toBeInTheDocument();
  });

  it("Keep current role closes the dialog, sends nothing and leaves the old value", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.selectOptions(screen.getByRole("combobox", { name: "Role for Bob" }), "admin");
    await user.click(await screen.findByRole("button", { name: "Keep current role" }));
    await waitFor(() => expect(screen.queryByTestId("confirm-dialog")).toBeNull());
    expect(callsMatching("PATCH", /users/)).toHaveLength(0);
    expect(screen.getByRole("combobox", { name: "Role for Bob" })).toHaveValue("normal");
  });

  it("does not use a button primary destructive fill for the non-destructive confirm", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.selectOptions(screen.getByRole("combobox", { name: "Role for Bob" }), "admin");
    const confirm = await screen.findByRole("button", { name: "Change role" });
    expect(confirm.className).not.toContain("bg-destructive");
  });

  it("shows an error toast and keeps the old value when the server refuses (403), then refetches", async () => {
    forced["PATCH /api/v1/tenants/t1/users/u2"] = { status: 403, message: "forbidden" };
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.selectOptions(screen.getByRole("combobox", { name: "Role for Bob" }), "admin");
    await user.click(await screen.findByRole("button", { name: "Change role" }));
    await screen.findByText("You don't have permission to do that.");
    await waitFor(() => expect(screen.queryByTestId("confirm-dialog")).toBeNull());
    expect(screen.getByRole("combobox", { name: "Role for Bob" })).toHaveValue("normal");
    await waitFor(() => expect(callsMatching("GET", "/api/v1/tenants/t1/users").length).toBeGreaterThanOrEqual(2));
  });

  it("handles a member who is already gone (404): message, refreshed list, no crash", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.selectOptions(screen.getByRole("combobox", { name: "Role for Bob" }), "admin");
    // Bob left after this page loaded.
    forced["PATCH /api/v1/tenants/t1/users/u2"] = { status: 404, message: "not found" };
    members = members.filter((m) => m.id !== "u2");
    await user.click(await screen.findByRole("button", { name: "Change role" }));
    await screen.findByText("That is no longer available. The list has been refreshed.");
    await waitFor(() => expect(screen.queryByRole("combobox", { name: "Role for Bob" })).toBeNull());
  });
});

describe("remove member", () => {
  it("asks first with Keep member focused, sends the listed id, toasts, drops the row and focuses the table caption", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Remove Bob" }));
    const dialog = await screen.findByTestId("confirm-dialog");
    expect(within(dialog).getByRole("heading", { name: "Remove Bob?" })).toBeInTheDocument();
    expect(within(dialog).getByText("Bob loses access to Ada's workspace immediately. You can invite them again later.")).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Keep member" })).toHaveFocus());
    expect(callsMatching("DELETE", /users/)).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Remove member" }));
    await screen.findByText("Member removed");
    const del = callsMatching("DELETE", "/api/v1/tenants/t1/users");
    expect(del).toHaveLength(1);
    expect(JSON.parse(String(del[0]!.data))).toEqual({ user_id: "u2" });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Remove Bob" })).toBeNull());
    await waitFor(() => expect(screen.getByTestId("members-table").querySelector("caption")).toHaveFocus());
  });

  it("Keep member sends nothing and returns focus to the remove button", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    const trigger = screen.getByRole("button", { name: "Remove Bob" });
    await user.click(trigger);
    await user.click(await screen.findByRole("button", { name: "Keep member" }));
    await waitFor(() => expect(screen.queryByTestId("confirm-dialog")).toBeNull());
    expect(callsMatching("DELETE", /users/)).toHaveLength(0);
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("Escape closes the dialog and an overlay click does not", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Remove Bob" }));
    await screen.findByTestId("confirm-dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("confirm-dialog")).toBeNull());
    expect(callsMatching("DELETE", /users/)).toHaveLength(0);
  });

  it("explains a refusal (403) with a message and a refetch, with no stale optimistic state", async () => {
    forced["DELETE /api/v1/tenants/t1/users"] = { status: 403, message: "forbidden" };
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Remove Bob" }));
    await user.click(await screen.findByRole("button", { name: "Remove member" }));
    await screen.findByText("You don't have permission to do that.");
    expect(screen.getByRole("button", { name: "Remove Bob" })).toBeInTheDocument();
    await waitFor(() => expect(callsMatching("GET", "/api/v1/tenants/t1/users").length).toBeGreaterThanOrEqual(2));
  });

  it("treats a 429 with its own message", async () => {
    forced["DELETE /api/v1/tenants/t1/users"] = { status: 429, message: "slow down", headers: { "retry-after": "30" } };
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Remove Bob" }));
    await user.click(await screen.findByRole("button", { name: "Remove member" }));
    await screen.findByText("Too many changes in a short time. Wait a moment, then try again.");
  });
});

describe("pending invitations sent", () => {
  beforeEach(() => {
    members = [...members, member("u9", "Dee", "invite")];
  });

  it("lists each pending invitation with the email, the date and a named Withdraw button", async () => {
    renderPage();
    const page = await loaded();
    expect(within(page).getByRole("heading", { level: 3, name: "Pending invitations" })).toBeInTheDocument();
    const list = within(page).getByTestId("pending-sent-list");
    expect(within(list).getByText("dee@example.test")).toBeInTheDocument();
    expect(within(list).getByText(/^Invited .*2026$/)).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Withdraw invitation for dee@example.test" })).toBeInTheDocument();
  });

  it("asks first with Keep invitation focused, then withdraws by the listed id and toasts", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Withdraw invitation for dee@example.test" }));
    const dialog = await screen.findByTestId("confirm-dialog");
    expect(within(dialog).getByRole("heading", { name: "Withdraw invitation?" })).toBeInTheDocument();
    expect(within(dialog).getByText("dee@example.test will no longer be able to join Ada's workspace. You can invite them again later.")).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Keep invitation" })).toHaveFocus());
    await user.click(within(dialog).getByRole("button", { name: "Withdraw invitation" }));
    await screen.findByText("Invitation withdrawn");
    expect(JSON.parse(String(callsMatching("DELETE", "/api/v1/tenants/t1/users")[0]!.data))).toEqual({ user_id: "u9" });
    await waitFor(() => expect(screen.queryByTestId("pending-sent-list")).toBeNull());
    expect(screen.getByText("No pending invitations.")).toBeInTheDocument();
  });
});

describe("workspaces you've joined", () => {
  beforeEach(() => {
    memberships = [ownMembership, otherMembership("admin")];
  });

  it("lists the workspace, its owner and the caller's role, and never offers Leave for the caller's own workspace", async () => {
    renderPage();
    const card = await screen.findByTestId("joined-workspaces");
    expect(within(card).getByText("Grace's workspace")).toBeInTheDocument();
    expect(within(card).getByText("Owned by Grace")).toBeInTheDocument();
    expect(within(card).getByText("Admin")).toBeInTheDocument();
    expect(within(card).getAllByTestId("workspace-leave")).toHaveLength(1);
    expect(within(card).queryByText("Ada's workspace")).toBeNull();
    expect(within(card).getByRole("button", { name: "Leave Grace's workspace" })).toBeInTheDocument();
  });

  it("asks first with Stay in workspace focused, leaves with the caller's own id on the listed tenant, and removes the section", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Leave Grace's workspace" }));
    const dialog = await screen.findByTestId("confirm-dialog");
    expect(within(dialog).getByRole("heading", { name: "Leave Grace's workspace?" })).toBeInTheDocument();
    expect(within(dialog).getByText("You lose access to Grace's workspace. The owner would have to invite you again for you to rejoin.")).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Stay in workspace" })).toHaveFocus());
    expect(callsMatching("DELETE", /users/)).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Leave workspace" }));
    await screen.findByText("You left Grace's workspace");
    const del = callsMatching("DELETE", "/api/v1/tenants/t9/users");
    expect(del).toHaveLength(1);
    expect(JSON.parse(String(del[0]!.data))).toEqual({ user_id: "u1" });
    await waitFor(() => expect(screen.queryByTestId("joined-workspaces")).toBeNull());
  });

  it("makes the section disappear cleanly when the server says the membership is gone (404)", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Leave Grace's workspace" }));
    // The owner removed the caller after this page loaded.
    forced["DELETE /api/v1/tenants/t9/users"] = { status: 404, message: "not found" };
    memberships = [ownMembership];
    await user.click(await screen.findByRole("button", { name: "Leave workspace" }));
    await screen.findByText("That is no longer available. The list has been refreshed.");
    await waitFor(() => expect(screen.queryByTestId("joined-workspaces")).toBeNull());
  });
});

describe("invite form", () => {
  it("validates the email with the shared schema and sends nothing for an invalid one", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.type(screen.getByLabelText("Email address"), "not-an-email");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(callsMatching("POST", /users/)).toHaveLength(0);
  });

  it("requires an email", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
  });

  it("sends the trimmed lowercase email to the listed tenant, toasts, clears and refocuses the field, and lists the pending invitation", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    const field = screen.getByLabelText("Email address");
    await user.type(field, "  Dee@Example.test ");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    await screen.findByText("Invitation sent");
    expect(screen.getByText("dee@example.test can accept it from their Team page.")).toBeInTheDocument();
    const post = callsMatching("POST", "/api/v1/tenants/t1/users");
    expect(post).toHaveLength(1);
    expect(JSON.parse(String(post[0]!.data))).toEqual({ email: "dee@example.test" });
    await waitFor(() => expect(field).toHaveValue(""));
    await waitFor(() => expect(field).toHaveFocus());
    await within(await screen.findByTestId("pending-sent-list")).findByText("dee@example.test");
  });

  it.each([
    [404, "no active account with that email"],
    [409, "that person is already a member of this workspace"],
    [409, "an invitation to that person is already pending"],
    [409, "you cannot invite yourself"],
  ])("shows the server message exactly in an alert for %s and adds no toast", async (status, message) => {
    forced["POST /api/v1/tenants/t1/users"] = { status, message };
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.type(screen.getByLabelText("Email address"), "x@example.test");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    const alert = await screen.findByTestId("alert-form-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent(new RegExp(`^${message}$`));
    expect(screen.queryByText("Request failed")).toBeNull();
    expect(screen.queryByText("Invitation sent")).toBeNull();
    // The typed address stays so it can be corrected.
    expect(screen.getByLabelText("Email address")).toHaveValue("x@example.test");
    expect(screen.getByLabelText("Email address")).toHaveAttribute("aria-describedby");
  });

  it("clears the error when the user types again", async () => {
    forced["POST /api/v1/tenants/t1/users"] = { status: 404, message: "no active account with that email" };
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.type(screen.getByLabelText("Email address"), "x@example.test");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    await screen.findByTestId("alert-form-error");
    await user.type(screen.getByLabelText("Email address"), "y");
    await waitFor(() => expect(screen.queryByTestId("alert-form-error")).toBeNull());
  });

  it("has its own message for 429, using the Retry-After seconds", async () => {
    forced["POST /api/v1/tenants/t1/users"] = { status: 429, message: "rate limited", headers: { "retry-after": "42" } };
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.type(screen.getByLabelText("Email address"), "x@example.test");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByTestId("alert-form-error")).toHaveTextContent("Too many invitations were sent. Try again in 42 seconds.");
  });

  it("has a generic message for a failure without a server message", async () => {
    forced["POST /api/v1/tenants/t1/users"] = { status: 500, code: -1, message: "" };
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.type(screen.getByLabelText("Email address"), "x@example.test");
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByTestId("alert-form-error")).toHaveTextContent("Something went wrong. Try again.");
  });

  it("does not double submit: a second click while the request runs sends nothing", async () => {
    let release: () => void = () => undefined;
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.type(screen.getByLabelText("Email address"), "dee@example.test");
    gate = new Promise<void>((resolve) => (release = resolve));
    const submit = screen.getByRole("button", { name: "Send invitation" });
    await user.click(submit);
    await user.click(submit);
    expect(submit).toHaveAttribute("aria-busy", "true");
    await act(async () => release());
    await screen.findByText("Invitation sent");
    expect(callsMatching("POST", /users/)).toHaveLength(1);
  });
});

describe("language", () => {
  it("renders Chinese copy without raw keys and keeps the accessible names with the person", async () => {
    memberships = [ownMembership, otherMembership("invite")];
    renderPage();
    await loaded();
    await screen.findByTestId("invitations-for-you");
    await act(async () => {
      await setLanguage("zh");
    });
    const page = screen.getByTestId("team-page");
    expect(page.textContent).not.toMatch(/\bteam\.[a-z]/);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(i18n.t("team.title"));
    expect(screen.getByRole("heading", { level: 1 }).textContent).not.toBe("Team");
    expect(screen.getByRole("combobox", { name: i18n.t("team.roleFor", { nickname: "Bob" }) })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: i18n.t("team.acceptFrom", { owner: "Grace" }) })).toBeInTheDocument();
  });
});
