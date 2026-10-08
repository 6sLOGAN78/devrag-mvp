import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { AvatarInitials, avatarDataUrl, initialsOf } from "@/components/avatar-initials";
import { RequireAuth } from "@/components/require-auth";
import { Toaster } from "@/components/ui/sonner";
import { UserMenu } from "@/components/user-menu";
import { logoutPath } from "@/constants/api-paths";
import i18n, { setLanguage } from "@/i18n";
import { http, registerNavigate, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, setAuthorization } from "@/utils/authorization";

const originalAdapter = http.defaults.adapter;
const PNG = "data:image/png;base64,iVBORw0KGgo=";

const userDto = {
  id: "u1",
  nickname: "Ada Lovelace",
  email: "ada@example.test",
  avatar: "",
  language: "English",
  color_schema: "Bright",
  tenant_id: "t1",
  tenant_name: "Ada's workspace",
  role: "owner",
  is_superuser: false,
};

let logoutMode: "ok" | "network" | "500" | "401" | "pending" = "ok";
let calls: InternalAxiosRequestConfig[] = [];
let userOverrides: Partial<typeof userDto> = {};

const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  const done = (status: number, data: unknown) =>
    ({ data, status, statusText: String(status), headers: new AxiosHeaders(), config }) as never;
  if (config.url === "/v1/user/info") return Promise.resolve(done(200, { code: 0, message: "", data: { ...userDto, ...userOverrides } }));
  if (config.url === logoutPath) {
    if (logoutMode === "pending") return new Promise<never>(() => undefined);
    if (logoutMode === "network") return Promise.reject(new AxiosError("Network Error", "ERR_NETWORK", config));
    if (logoutMode === "401") {
      const response = done(401, { code: 401, message: "Unauthorized", data: null });
      return Promise.reject(new AxiosError("status 401", "ERR_BAD_REQUEST", config, null, response));
    }
    if (logoutMode === "500") {
      const response = done(500, { code: 500, message: "boom", data: null });
      return Promise.reject(new AxiosError("status 500", "ERR_BAD_RESPONSE", config, null, response));
    }
    return Promise.resolve(done(200, { code: 0, message: "", data: null }));
  }
  return Promise.reject(new AxiosError("Network Error", "ERR_NETWORK", config));
};

function Probe() {
  const location = useLocation();
  return (
    <p data-testid="login-page">
      {location.pathname}
      {location.search}
    </p>
  );
}

function renderGuarded() {
  const router = createMemoryRouter(
    [
      { element: <RequireAuth />, children: [{ path: "/system-status", element: <UserMenu /> }] },
      { path: "/login", element: <Probe /> },
    ],
    { initialEntries: ["/system-status"] },
  );
  const client = new QueryClient();
  registerQueryClient(client);
  registerNavigate({
    navigate: (to) => router.navigate(to, { replace: true }),
    currentPath: () => `${router.state.location.pathname}${router.state.location.search}`,
  });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
  return { router, client };
}

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});
beforeEach(() => {
  logoutMode = "ok";
  calls = [];
  userOverrides = {};
  useUserStore.getState().reset();
  setAuthorization("tok-a");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  registerNavigate(null);
});

describe("avatar helpers", () => {
  it.each([
    ["Ada Lovelace", "ada@example.test", "AL"],
    ["ada", "ada@example.test", "A"],
    ["  ", "zed@example.test", "Z"],
    ["", "", "?"],
    ["李 雷", "", "李雷"],
  ])("initialsOf(%j, %j) is %j", (nickname, email, expected) => {
    expect(initialsOf(nickname, email)).toBe(expected);
  });

  it.each([
    [PNG, PNG],
    ["data:image/jpeg;base64,/9j/4AAQ", "data:image/jpeg;base64,/9j/4AAQ"],
    ["data:image/gif;base64,R0lGODlh", "data:image/gif;base64,R0lGODlh"],
    ["data:image/webp;base64,UklGRg==", "data:image/webp;base64,UklGRg=="],
    ["data:image/svg+xml;base64,PHN2Zz4=", null],
    ["data:image/svg+xml;utf8,<svg onload=alert(1)>", null],
    ["https://evil.example/a.png", null],
    ["http://evil.example/a.png", null],
    ["javascript:alert(1)", null],
    ["data:text/html;base64,PHNjcmlwdD4=", null],
    ["data:image/png;base64,AAAA\"onerror=alert(1)", null],
    ["data:image/png;base64,", null],
    ["", null],
  ])("avatarDataUrl(%j) is %j", (value, expected) => {
    expect(avatarDataUrl(value)).toBe(expected);
  });

  it("renders an img only for an allowed data URL, decorative", () => {
    const { container, rerender } = render(<AvatarInitials avatar={PNG} nickname="Ada" email="a@example.test" />);
    const img = container.querySelector("img");
    expect(img).toHaveAttribute("src", PNG);
    expect(img).toHaveAttribute("alt", "");
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
    for (const bad of ["https://evil.example/a.png", "data:image/svg+xml;base64,PHN2Zz4=", "javascript:alert(1)"]) {
      rerender(<AvatarInitials avatar={bad} nickname="Ada Lovelace" email="a@example.test" />);
      expect(container.querySelector("img")).toBeNull();
      expect(container).toHaveTextContent("AL");
    }
  });

  it("renders hostile nickname text as text, never as markup", () => {
    const { container } = render(<AvatarInitials avatar="" nickname={'<img src=x onerror="alert(1)">'} email="" />);
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("UserMenu", () => {
  it("renders nothing without a signed-in user", () => {
    const router = createMemoryRouter([{ path: "/", element: <UserMenu /> }]);
    render(<RouterProvider router={router} />);
    expect(screen.queryByTestId("user-menu")).toBeNull();
  });

  it("has an accessible name and shows the nickname and email as text, with initials in the trigger", async () => {
    renderGuarded();
    const trigger = await screen.findByRole("button", { name: "Account menu" });
    expect(trigger).toHaveAttribute("data-testid", "user-menu");
    expect(trigger).toHaveTextContent("AL");
    expect(trigger.querySelector("img")).toBeNull();
    await userEvent.click(trigger);
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("Ada Lovelace")).toBeInTheDocument();
    expect(within(menu).getByText("ada@example.test")).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: "Sign out" })).toHaveAttribute("data-testid", "user-menu-signout");
    expect(within(menu).getAllByRole("menuitem")).toHaveLength(2);
    const profile = within(menu).getByRole("menuitem", { name: "Profile" });
    expect(profile).toHaveAttribute("href", "/user-setting/profile");
    expect(profile).toHaveAttribute("data-testid", "user-menu-profile");
  });

  it("is operable by keyboard: Enter opens it, Escape closes it and returns focus to the trigger", async () => {
    renderGuarded();
    const trigger = await screen.findByTestId("user-menu");
    trigger.focus();
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitUntil(() => screen.queryByRole("menu") === null, { describe: "menu closed" });
    expect(trigger).toHaveFocus();
  });

  it("shows a data-URL avatar in an img and falls back to initials for anything else", async () => {
    userOverrides = { avatar: PNG };
    renderGuarded();
    const trigger = await screen.findByTestId("user-menu");
    expect(trigger.querySelector("img")).toHaveAttribute("src", PNG);
    useUserStore.getState().setUser({ ...useUserStore.getState().user!, avatar: "https://evil.example/a.png" });
    await waitUntil(() => trigger.querySelector("img") === null, { describe: "avatar fell back" });
    expect(trigger).toHaveTextContent("AL");
  });

  it("renders a hostile nickname and email as text only", async () => {
    userOverrides = { nickname: '<b id="x">Bob</b><script>alert(1)</script>', email: '"><img src=x onerror=alert(1)>@e.test' };
    renderGuarded();
    await userEvent.click(await screen.findByTestId("user-menu"));
    const menu = await screen.findByRole("menu");
    expect(menu.querySelector("script, b, img")).toBeNull();
    expect(within(menu).getByText('<b id="x">Bob</b><script>alert(1)</script>')).toBeInTheDocument();
  });

  it("follows the language", async () => {
    await setLanguage("zh");
    renderGuarded();
    await userEvent.click(await screen.findByRole("button", { name: i18n.t("header.accountMenu") }));
    expect(i18n.t("header.accountMenu")).not.toBe("Account menu");
    expect(await screen.findByRole("menuitem", { name: i18n.t("header.signOut") })).toBeInTheDocument();
    expect(i18n.t("header.signOut")).not.toBe("Sign out");
  });
});

describe("UserMenu sign out (T-02-53B)", () => {
  async function signOut() {
    const view = renderGuarded();
    view.client.setQueryData(["other"], 1);
    await userEvent.click(await screen.findByTestId("user-menu"));
    await userEvent.click(await screen.findByTestId("user-menu-signout"));
    return view;
  }

  it("calls logout with the bearer token, then purges everything and lands on a bare /login with no toast", async () => {
    const view = await signOut();
    expect(await screen.findByTestId("login-page")).toHaveTextContent(/^\/login$/);
    const logout = calls.find((c) => c.url === logoutPath);
    expect(logout?.method).toBe("post");
    expect(new AxiosHeaders(logout?.headers as never).get("Authorization")).toBe("Bearer tok-a");
    expect(logout?.url).not.toMatch(/tok-a/);
    expect(getAuthorization()).toBeNull();
    expect(useUserStore.getState().user).toBeNull();
    expect(view.client.getQueryData(["other"])).toBeUndefined();
    expect(view.router.state.location.search).toBe("");
    expect(screen.queryByText("Session expired")).toBeNull();
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it.each([["a network error", "network" as const], ["a 500", "500" as const]])(
    "still signs out locally when logout fails with %s, with no toast",
    async (_name, mode) => {
      logoutMode = mode;
      const view = await signOut();
      expect(await screen.findByTestId("login-page")).toHaveTextContent(/^\/login$/);
      expect(getAuthorization()).toBeNull();
      expect(useUserStore.getState().user).toBeNull();
      expect(view.router.state.location.search).toBe("");
      expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    },
  );

  it("signing out with an expired token never shows 'Session expired' and never adds next, even though logout answers 401 (WR-F03)", async () => {
    logoutMode = "401";
    const visited: string[] = [];
    const view = renderGuarded();
    const unsubscribe = view.router.subscribe((state) => visited.push(`${state.location.pathname}${state.location.search}`));
    view.client.setQueryData(["other"], 1);
    await userEvent.click(await screen.findByTestId("user-menu"));
    await userEvent.click(await screen.findByTestId("user-menu-signout"));
    expect(await screen.findByTestId("login-page")).toHaveTextContent(/^\/login$/);
    unsubscribe();
    expect(calls.filter((c) => c.url === logoutPath)).toHaveLength(1);
    expect(getAuthorization()).toBeNull();
    expect(useUserStore.getState().user).toBeNull();
    expect(view.client.getQueryData(["other"])).toBeUndefined();
    expect(visited.filter((path) => path.includes("next="))).toEqual([]);
    expect(screen.queryByText("Session expired")).toBeNull();
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it("ignores a second activation while logout is in flight", async () => {
    logoutMode = "pending";
    renderGuarded();
    await userEvent.click(await screen.findByTestId("user-menu"));
    await userEvent.click(await screen.findByTestId("user-menu-signout"));
    await waitUntil(() => calls.some((c) => c.url === logoutPath), { describe: "logout request sent" });
    await userEvent.click(await screen.findByTestId("user-menu"));
    const again = screen.queryByTestId("user-menu-signout");
    if (again) await userEvent.click(again);
    expect(calls.filter((c) => c.url === logoutPath)).toHaveLength(1);
  });
});
