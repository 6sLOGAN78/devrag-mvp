import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { act } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import i18n, { setLanguage } from "@/i18n";
import type { SessionUser } from "@/interfaces/user";
import { http } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { setAuthorization } from "@/utils/authorization";
import HomePage from ".";

const USER: SessionUser = {
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

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let respond: (config: InternalAxiosRequestConfig) => Promise<unknown>;

const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  return respond(config) as never;
};
const listOf = (count: number) =>
  Array.from({ length: count }, (_, index) => ({ token: `ragflow-FAKE-${index}-0000000000000`, beta: "", create_time: 1_700_000_000_000 + index }));
const person = (id: string, role: string) => ({ id, nickname: id, email: `${id}@example.test`, avatar: "", role, joined_time: "2026-10-01T12:00:00Z" });
const entry = (tenant_id: string, role: string) => ({ tenant_id, tenant_name: `Workspace ${tenant_id}`, owner_nickname: "Grace", owner_avatar: "", role, joined_time: "2026-10-01T12:00:00Z" });
// Two people and one pending invitation sent (the owner sees it); two invitations waiting for the caller.
const membersOf = () => [person("u1", "owner"), person("u2", "normal"), person("u3", "invite")];
const membershipsOf = () => [entry("t1", "owner"), entry("t8", "invite"), entry("t9", "invite"), entry("t7", "admin")];
const okList = (config: InternalAxiosRequestConfig, rows: unknown[]) =>
  Promise.resolve({ data: { code: 0, message: "", data: rows }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config });
/** The default server: tokens, the owner's members and the caller's workspace list, each by its real path. */
function serve(config: InternalAxiosRequestConfig): Promise<unknown> {
  if (config.url === "/api/v1/tenants/t1/users") return okList(config, membersOf());
  if (config.url === "/v1/tenant/list") return okList(config, membershipsOf());
  return okList(config, listOf(3));
}
const tokenCalls = () => calls.filter((c) => String(c.url).startsWith("/api/v1/system/tokens"));
const failed = (config: InternalAxiosRequestConfig, status: number) =>
  Promise.reject(
    new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config, null, {
      data: { code: status, message: "x", data: null },
      status,
      statusText: String(status),
      headers: new AxiosHeaders(),
      config,
    } as never),
  );

function renderHome() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useUserStore.getState().reset();
  calls = [];
  respond = serve;
  setAuthorization("tok-a");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
});

describe("home dashboard (UI-09)", () => {
  it("makes the page title the first read element and shows the workspace line from the user's real data", () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    const page = screen.getByTestId("home-page");
    const title = within(page).getByRole("heading", { level: 1 });
    expect(title).toHaveTextContent("Welcome, Ada");
    expect(page.firstElementChild?.contains(title)).toBe(true);
    expect(within(page).getByText("Workspace: Ada's workspace")).toBeInTheDocument();
    expect(document.title).toBe("Home - devRag");
  });

  it.each([
    ["owner", "Owner"],
    ["admin", "Admin"],
    ["normal", "Member"],
    ["member", "Member"],
  ])("shows the %s role as %s in the role card", (role, label) => {
    useUserStore.getState().setUser({ ...USER, role });
    renderHome();
    const card = screen.getByTestId("stat-role");
    expect(card).toHaveTextContent("Your role");
    expect(card).toHaveTextContent(label);
  });

  it("shows loading skeletons and no title until the user is known", () => {
    renderHome();
    expect(screen.getByTestId("home-skeleton")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: /Welcome/ })).toBeNull();
    expect(screen.queryByTestId("stat-role")).toBeNull();
  });

  it("shows the four stat cards in order and every link, with no placeholder text", async () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    await waitFor(() => expect(screen.getByTestId("stat-invitations")).toHaveTextContent("2"));
    await waitFor(() => expect(screen.getByTestId("stat-members")).toHaveTextContent("2"));
    await waitFor(() => expect(screen.getByTestId("stat-tokens")).toHaveTextContent("3"));
    const cards = ["stat-role", "stat-members", "stat-tokens", "stat-invitations"].map((id) => screen.getByTestId(id));
    expect(cards[0]!.compareDocumentPosition(cards[1]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(cards[1]!.compareDocumentPosition(cards[2]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(cards[2]!.compareDocumentPosition(cards[3]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const links = screen.queryAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/user-setting/team",
      "/user-setting/team",
      "/user-setting/api",
      "/user-setting/team",
      "/user-setting/profile",
      "/user-setting/api",
      "/user-setting/team",
    ]);
    expect(screen.queryByText(/coming soon/i)).toBeNull();
  });

  it("links the role card to the team page", () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    expect(within(screen.getByTestId("stat-role")).getByRole("link")).toHaveAttribute("href", "/user-setting/team");
  });

  it("counts team members from the real list (people only, not invitations sent) and links to the team page", async () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    const card = screen.getByTestId("stat-members");
    await waitFor(() => expect(card).toHaveTextContent("2"));
    expect(card).toHaveTextContent("Team members");
    expect(within(card).getByRole("link")).toHaveAttribute("href", "/user-setting/team");
    expect(calls.map((c) => c.url)).toContain("/api/v1/tenants/t1/users");
  });

  it("counts invitations waiting for the caller from the workspace list and links to the team page", async () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    const card = screen.getByTestId("stat-invitations");
    await waitFor(() => expect(card).toHaveTextContent("2"));
    expect(card).toHaveTextContent("Pending invitations");
    expect(within(card).getByRole("link")).toHaveAttribute("href", "/user-setting/team");
    expect(calls.map((c) => c.url)).toContain("/v1/tenant/list");
  });

  it("shows zeros honestly when there are no teammates or invitations", async () => {
    respond = (config) => {
      if (config.url === "/api/v1/tenants/t1/users") return okList(config, [person("u1", "owner")]);
      if (config.url === "/v1/tenant/list") return okList(config, [entry("t1", "owner")]);
      return okList(config, []);
    };
    useUserStore.getState().setUser(USER);
    renderHome();
    await waitFor(() => expect(screen.getByTestId("stat-members")).toHaveTextContent("1"));
    await waitFor(() => expect(screen.getByTestId("stat-invitations")).toHaveTextContent("0"));
  });

  it("gives the members and invitations cards their own error with a retry that does not affect the others", async () => {
    respond = (config) => (config.url === "/api/v1/tenants/t1/users" || config.url === "/v1/tenant/list" ? failed(config, 500) : serve(config));
    const user = userEvent.setup();
    useUserStore.getState().setUser(USER);
    renderHome();
    const membersRetry = await screen.findByTestId("stat-members-retry");
    const invitationsRetry = await screen.findByTestId("stat-invitations-retry");
    expect(screen.getByTestId("stat-members")).toHaveTextContent("Couldn't load");
    await waitFor(() => expect(screen.getByTestId("stat-tokens")).toHaveTextContent("3"));
    respond = serve;
    await user.click(membersRetry);
    await waitFor(() => expect(screen.getByTestId("stat-members")).toHaveTextContent("2"));
    expect(screen.getByTestId("stat-invitations-retry")).toBe(invitationsRetry);
    await user.click(invitationsRetry);
    await waitFor(() => expect(screen.getByTestId("stat-invitations")).toHaveTextContent("2"));
  });

  it("shows the API tokens count from the real list as a whole-card link to the tokens page", async () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    const card = await screen.findByTestId("stat-tokens");
    await waitFor(() => expect(card).toHaveTextContent("3"));
    expect(card).toHaveTextContent("API tokens");
    expect(within(card).getByRole("link")).toHaveAttribute("href", "/user-setting/api");
    expect(tokenCalls().map((c) => c.url)).toEqual(["/api/v1/system/tokens"]);
    expect(card.textContent).not.toContain("ragflow-");
  });

  it("has a Manage API tokens link row", async () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    const link = within(screen.getByTestId("home-links")).getByRole("link", { name: "Manage API tokens" });
    expect(link).toHaveAttribute("href", "/user-setting/api");
    await waitFor(() => expect(screen.getByTestId("stat-tokens")).toHaveTextContent("3"));
  });

  it("shows a loading skeleton in the tokens card until the list arrives", async () => {
    let release: () => void = () => undefined;
    respond = (config) => (String(config.url).startsWith("/api/v1/system/tokens") ? new Promise((resolve) => (release = () => resolve(okList(config, listOf(1))))) : serve(config));
    useUserStore.getState().setUser(USER);
    renderHome();
    expect(screen.getByTestId("stat-tokens").querySelector('[aria-hidden="true"]')).not.toBeNull();
    await waitFor(() => expect(tokenCalls()).toHaveLength(1));
    await act(async () => release());
    await waitFor(() => expect(screen.getByTestId("stat-tokens")).toHaveTextContent("1"));
  });

  it("gives the tokens card its own error with a retry that does not affect the rest of the page", async () => {
    respond = (config) => (String(config.url).startsWith("/api/v1/system/tokens") ? failed(config, 500) : serve(config));
    const user = userEvent.setup();
    useUserStore.getState().setUser(USER);
    renderHome();
    const retry = await screen.findByTestId("stat-tokens-retry");
    expect(screen.getByTestId("stat-tokens")).toHaveTextContent("Couldn't load");
    expect(screen.getByTestId("stat-role")).toHaveTextContent("Owner");
    respond = (config) => (String(config.url).startsWith("/api/v1/system/tokens") ? okList(config, listOf(2)) : serve(config));
    await user.click(retry);
    await waitFor(() => expect(screen.getByTestId("stat-tokens")).toHaveTextContent("2"));
  });

  it.each(["admin", "normal"])("hides the tokens card and link and sends no token request for the %s role, which cannot manage tokens", async (role) => {
    useUserStore.getState().setUser({ ...USER, role });
    renderHome();
    expect(screen.queryByTestId("stat-tokens")).toBeNull();
    expect(screen.queryByRole("link", { name: "Manage API tokens" })).toBeNull();
    await waitFor(() => expect(screen.getByTestId("stat-members")).toHaveTextContent("2"));
    expect(tokenCalls()).toHaveLength(0);
    // The team cards stay: every member can see the team and their own invitations.
    expect(screen.getByTestId("stat-invitations")).toBeInTheDocument();
  });

  it("has a Manage your team link row to the team page", async () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    const link = within(screen.getByTestId("home-links")).getByRole("link", { name: "Manage your team" });
    expect(link).toHaveAttribute("href", "/user-setting/team");
    expect(link.querySelector("svg")).not.toBeNull();
    await waitFor(() => expect(screen.getByTestId("stat-members")).toHaveTextContent("2"));
  });

  it("has a Manage your account card with an Edit your profile link row to the profile page", () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    const card = screen.getByTestId("home-links");
    expect(within(card).getByRole("heading", { level: 2, name: "Manage your account" })).toBeInTheDocument();
    const link = within(card).getByRole("link", { name: "Edit your profile" });
    expect(link).toHaveAttribute("href", "/user-setting/profile");
    expect(link.querySelector("svg")).not.toBeNull();
  });

  it("does not render the account links while the user is loading", () => {
    renderHome();
    expect(screen.queryByTestId("home-links")).toBeNull();
  });

  it("renders text only: a hostile nickname is never interpreted as markup", () => {
    useUserStore.getState().setUser({ ...USER, nickname: "<img src=x onerror=alert(1)>" });
    renderHome();
    expect(screen.getByTestId("home-page").querySelector("img")).toBeNull();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome, <img src=x onerror=alert(1)>");
  });

  it("follows the language switch", async () => {
    useUserStore.getState().setUser(USER);
    renderHome();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome, Ada");
    await act(async () => {
      await setLanguage("zh");
    });
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(i18n.t("home.title", { nickname: "Ada" }));
    expect(screen.getByRole("heading", { level: 1 }).textContent).not.toContain("Welcome");
  });
});
