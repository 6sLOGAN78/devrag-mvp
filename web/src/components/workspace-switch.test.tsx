import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { WorkspaceSwitch } from "@/components/workspace-switch";
import { Toaster } from "@/components/ui/sonner";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";

// Drives the real component, hook, service and HTTP client against an in-memory GET /v1/tenant/list. Fake data only.
const ME: SessionUser = {
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
const row = (tenant_id: string, tenant_name: string, role: string, owner_nickname: string): Row => ({
  tenant_id,
  tenant_name,
  owner_nickname,
  owner_avatar: "",
  role,
  joined_time: "2026-10-01T12:00:00Z",
});

const originalAdapter = http.defaults.adapter;
let rows: Row[] = [];
let listStatus = 200;
let client: QueryClient;

const adapter: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
  if (config.url === "/v1/tenant/list") {
    if (listStatus !== 200) {
      const response = { data: { code: listStatus, message: "nope", data: null }, status: listStatus, statusText: String(listStatus), headers: new AxiosHeaders(), config } as never;
      return Promise.reject(new AxiosError(`status ${listStatus}`, "ERR_BAD_RESPONSE", config, null, response));
    }
    return Promise.resolve({ data: { code: 0, message: "", data: rows }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config } as never);
  }
  return Promise.reject(new AxiosError("Network Error", "ERR_NETWORK", config));
};

function renderSwitch() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <WorkspaceSwitch />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

beforeEach(() => {
  rows = [row("t1", "Ada's workspace", "owner", "Ada")];
  listStatus = 200;
  useWorkspaceStore.getState().reset();
  useUserStore.getState().reset();
  useUserStore.getState().setUser(ME);
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("WorkspaceSwitch with one workspace (D-26)", () => {
  it("shows the name as plain text with a visually hidden Workspace: prefix and no menu", async () => {
    renderSwitch();
    const current = await screen.findByTestId("workspace-current");
    expect(current).toHaveTextContent("Workspace:Ada's workspace");
    expect(within(current).getByText("Workspace:")).toHaveClass("sr-only");
    expect(screen.queryByTestId("workspace-switch")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("stays plain text when the only other rows are pending invitations", async () => {
    rows = [row("t1", "Ada's workspace", "owner", "Ada"), row("t8", "Hal's workspace", "invite", "Hal")];
    renderSwitch();
    await waitFor(() => expect(client.isFetching()).toBe(0));
    expect(screen.getByTestId("workspace-current")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("stays plain text with no error UI when the list request fails", async () => {
    listStatus = 500;
    renderSwitch();
    await waitFor(() => expect(client.isFetching()).toBe(0));
    expect(screen.getByTestId("workspace-current")).toHaveTextContent("Ada's workspace");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("WorkspaceSwitch with several workspaces (D-26)", () => {
  beforeEach(() => {
    rows = [
      row("t9", "Grace's workspace", "admin", "Grace"),
      row("t1", "Ada's workspace", "owner", "Ada"),
      row("t8", "Hal's workspace", "invite", "Hal"),
      row("t7", "Alan's workspace", "normal", "Alan"),
    ];
  });

  it("upgrades to a button named after the active workspace once a joined workspace arrives", async () => {
    renderSwitch();
    const trigger = await screen.findByRole("button", { name: "Workspace: Ada's workspace. Change workspace" });
    expect(trigger).toHaveAttribute("data-testid", "workspace-switch");
    expect(screen.queryByTestId("workspace-current")).toBeNull();
  });

  it("lists own first, then joined workspaces by name, never an invite, as menuitemradio with aria-checked", async () => {
    const user = userEvent.setup();
    renderSwitch();
    await user.click(await screen.findByTestId("workspace-switch"));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("Workspaces")).toBeInTheDocument();
    const options = within(menu).getAllByRole("menuitemradio");
    expect(options.map((o) => o.getAttribute("data-testid"))).toEqual(["workspace-option-t1", "workspace-option-t7", "workspace-option-t9"]);
    expect(options.map((o) => o.getAttribute("aria-checked"))).toEqual(["true", "false", "false"]);
    expect(screen.queryByTestId("workspace-option-t8")).toBeNull();
    // Second line: the role alone for the own workspace, role and owner for a joined one.
    expect(options[0]).toHaveTextContent("Owner");
    expect(options[0]).not.toHaveTextContent("Owned by");
    expect(options[1]).toHaveTextContent("Member · Owned by Alan");
    expect(options[2]).toHaveTextContent("Admin · Owned by Grace");
    expect(options[0]!.querySelector("svg")).not.toBeNull();
    expect(within(menu).getByRole("separator")).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: "Manage team" })).toHaveAttribute("href", "/user-setting/team");
  });

  it("switches, persists {userId, tenantId}, announces without a toast and keeps focus on the trigger", async () => {
    const user = userEvent.setup();
    renderSwitch();
    const trigger = await screen.findByTestId("workspace-switch");
    await user.click(trigger);
    await user.click(await screen.findByTestId("workspace-option-t9"));
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t9");
    expect(JSON.parse(localStorage.getItem("devrag.workspace") ?? "null")).toEqual({ userId: "u1", tenantId: "t9" });
    const status = screen.getByTestId("workspace-announcer");
    expect(status).toHaveAttribute("role", "status");
    expect(status).toHaveTextContent("Switched to Grace's workspace");
    expect(status).toHaveClass("sr-only");
    expect(screen.getByTestId("workspace-switch")).toHaveAccessibleName("Workspace: Grace's workspace. Change workspace");
    await waitFor(() => expect(screen.getByTestId("workspace-switch")).toHaveFocus());
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    await user.click(screen.getByTestId("workspace-switch"));
    expect(await screen.findByTestId("workspace-option-t9")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("workspace-option-t1")).toHaveAttribute("aria-checked", "false");
  });

  it("restores the stored workspace of the same user and ignores one stored for another user", async () => {
    localStorage.setItem("devrag.workspace", JSON.stringify({ userId: "u1", tenantId: "t7" }));
    const first = renderSwitch();
    expect(await screen.findByRole("button", { name: "Workspace: Alan's workspace. Change workspace" })).toBeInTheDocument();
    first.unmount();
    useWorkspaceStore.getState().reset();
    localStorage.setItem("devrag.workspace", JSON.stringify({ userId: "someone-else", tenantId: "t7" }));
    renderSwitch();
    expect(await screen.findByRole("button", { name: "Workspace: Ada's workspace. Change workspace" })).toBeInTheDocument();
  });

  it("falls back to the own workspace with an info toast when the active workspace disappears", async () => {
    const user = userEvent.setup();
    renderSwitch();
    await user.click(await screen.findByTestId("workspace-switch"));
    await user.click(await screen.findByTestId("workspace-option-t9"));
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t9");

    rows = [row("t1", "Ada's workspace", "owner", "Ada"), row("t7", "Alan's workspace", "normal", "Alan")];
    await client.invalidateQueries();
    expect(await screen.findByText("You no longer have access to Grace's workspace")).toBeInTheDocument();
    expect(screen.getByText("Switched to your own workspace.")).toBeInTheDocument();
    expect(useWorkspaceStore.getState().activeTenantId).toBe("t1");
    expect(screen.getByTestId("workspace-switch")).toHaveAccessibleName("Workspace: Ada's workspace. Change workspace");
    expect(useWorkspaceStore.getState().lost).toBeNull();
  });

  it("renders workspace and owner names as text, never as markup", async () => {
    rows = [row("t1", "Ada's workspace", "owner", "Ada"), row("t7", "<img src=x onerror=alert(1)>", "normal", "<b>Mallory</b>")];
    const user = userEvent.setup();
    const { container } = renderSwitch();
    await user.click(await screen.findByTestId("workspace-switch"));
    const option = await screen.findByTestId("workspace-option-t7");
    expect(option).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(option).toHaveTextContent("<b>Mallory</b>");
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
  });

  it("does not list invite rows even for a stored invitation id", async () => {
    localStorage.setItem("devrag.workspace", JSON.stringify({ userId: "u1", tenantId: "t8" }));
    renderSwitch();
    expect(await screen.findByRole("button", { name: "Workspace: Ada's workspace. Change workspace" })).toBeInTheDocument();
  });
});
