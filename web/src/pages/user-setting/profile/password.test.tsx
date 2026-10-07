import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RequireAuth } from "@/components/require-auth";
import { Toaster } from "@/components/ui/sonner";
import { userPasswordPath } from "@/constants/api-paths";
import { http, registerNavigate, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, setAuthorization } from "@/utils/authorization";
import ProfilePage from ".";

const originalAdapter = http.defaults.adapter;

const userDto = {
  id: "u1",
  nickname: "Ada Lovelace",
  email: "ada@example.test",
  avatar: "",
  language: "en",
  color_schema: "Bright",
  tenant_id: "t1",
  tenant_name: "Ada's workspace",
  role: "owner",
  is_superuser: false,
};

// Obviously fake values, built here so no literal looks like a credential.
const OLD = ["old", "pass", "0001"].join("-");
const NEW = ["new", "pass", "0002"].join("-");

type Responder = (config: InternalAxiosRequestConfig) => Promise<unknown> | unknown;
let calls: InternalAxiosRequestConfig[] = [];
let changeResponder: Responder;
let infoStatus: 200 | 401 = 200;

const done = (config: InternalAxiosRequestConfig, status: number, data: unknown) =>
  ({ data, status, statusText: String(status), headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, status: number, code: number, message: string) {
  return Promise.reject(new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config, null, done(config, status, { code, message, data: null })));
}

const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  if (config.url === "/v1/user/info") {
    return infoStatus === 200 ? Promise.resolve(done(config, 200, { code: 0, message: "", data: userDto })) : failure(config, 401, 401, "expired");
  }
  if (config.url === userPasswordPath) return Promise.resolve(changeResponder(config)) as never;
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

function renderPage() {
  const router = createMemoryRouter(
    [
      { element: <RequireAuth />, children: [{ path: "/user-setting/profile", element: <ProfilePage /> }] },
      { path: "/login", element: <Probe /> },
    ],
    { initialEntries: ["/user-setting/profile"] },
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

const card = () => within(screen.getByTestId("password-form"));
const current = () => screen.getByLabelText("Current password");
const fresh = () => screen.getByLabelText("New password", { exact: true });
const confirm = () => screen.getByLabelText("Confirm new password");
const submit = () => screen.getByRole("button", { name: "Change password" });
const changeCalls = () => calls.filter((c) => c.url === userPasswordPath);

async function ready() {
  const view = renderPage();
  await screen.findByTestId("password-form");
  return view;
}
async function fill(old: string, next: string, again = next) {
  const user = userEvent.setup();
  if (old !== "") await user.type(current(), old);
  if (next !== "") await user.type(fresh(), next);
  if (again !== "") await user.type(confirm(), again);
  return user;
}

beforeEach(() => {
  calls = [];
  infoStatus = 200;
  changeResponder = (config) => done(config, 200, { code: 0, message: "", data: null });
  useUserStore.getState().reset();
  setAuthorization("tok-a");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  registerNavigate(null);
  vi.restoreAllMocks();
});

describe("password card (D-02, D-08)", () => {
  it("is a second card with its title, helper, the sign-out note and the right autocomplete values", async () => {
    await ready();
    expect(screen.getByRole("heading", { level: 2, name: "Password" })).toBeInTheDocument();
    expect(current()).toHaveAttribute("autocomplete", "current-password");
    expect(fresh()).toHaveAttribute("autocomplete", "new-password");
    expect(confirm()).toHaveAttribute("autocomplete", "new-password");
    for (const field of [current(), fresh(), confirm()]) expect(field).toHaveAttribute("type", "password");
    expect(card().getByText("At least 8 characters.")).toBeInTheDocument();
    expect(card().getByText("Changing your password signs you out on every device. Signing out on any device also signs you out everywhere.")).toBeInTheDocument();
    expect(card().getAllByTestId("password-toggle")).toHaveLength(3);
    expect(submit()).toHaveAttribute("type", "submit");
    // The profile card keeps its own primary action: two cards, two forms.
    expect(screen.getByTestId("profile-form")).not.toContainElement(submit());
  });

  it.each([
    [7, false, "Use at least 8 characters."],
    [8, true, null],
    [128, true, null],
    [129, false, "Use 128 characters or fewer."],
  ] as const)("a new password of %i characters: accepted=%s", async (size, accepted, message) => {
    await ready();
    const user = userEvent.setup();
    const value = "a".repeat(size);
    await user.type(current(), OLD);
    await user.click(fresh());
    await user.paste(value);
    await user.click(confirm());
    await user.paste(value);
    await user.click(submit());
    if (accepted) {
      await waitUntil(() => changeCalls().length === 1, { describe: "password request" });
      expect(JSON.parse(String(changeCalls()[0]!.data))).toEqual({ old_password: OLD, new_password: value });
    } else {
      expect(await screen.findByText(message!)).toBeInTheDocument();
      expect(fresh()).toHaveAttribute("aria-invalid", "true");
      expect(changeCalls()).toHaveLength(0);
    }
  });

  it("requires the current password and a matching confirmation, and sends nothing until both are right", async () => {
    await ready();
    const user = await fill("", NEW, NEW);
    await user.click(submit());
    expect(await screen.findByText("Enter your password.")).toBeInTheDocument();
    expect(current()).toHaveAttribute("aria-invalid", "true");
    await user.type(current(), OLD);
    await user.clear(confirm());
    await user.type(confirm(), `${NEW}x`);
    await user.click(submit());
    expect(await screen.findByText("The passwords don't match.")).toBeInTheDocument();
    expect(confirm()).toHaveAttribute("aria-invalid", "true");
    expect(confirm()).toHaveAttribute("aria-describedby");
    expect(changeCalls()).toHaveLength(0);
  });

  it("sends exactly old_password and new_password with the bearer token, silently", async () => {
    await ready();
    const user = await fill(OLD, NEW);
    await user.click(submit());
    await waitUntil(() => changeCalls().length === 1, { describe: "password request" });
    const request = changeCalls()[0]!;
    expect(request.method).toBe("post");
    expect(request.silent).toBe(true);
    expect(JSON.parse(String(request.data))).toEqual({ old_password: OLD, new_password: NEW });
    expect(new AxiosHeaders(request.headers as never).get("Authorization")).toBe("Bearer tok-a");
    expect(request.url).not.toContain(OLD);
    expect(request.url).not.toContain(NEW);
  });

  it("a wrong current password (400) shows the server message in the alert, marks the field, and does NOT sign the user out", async () => {
    changeResponder = (config) => failure(config, 400, 101, "current password is incorrect");
    const { router } = await ready();
    const user = await fill(OLD, NEW);
    await user.click(submit());
    const alert = await screen.findByTestId("alert-password-error");
    expect(alert).toHaveTextContent("current password is incorrect");
    expect(alert).toHaveAttribute("role", "alert");
    expect(current()).toHaveAttribute("aria-invalid", "true");
    expect(current()).toHaveAttribute("aria-describedby", alert.getAttribute("id"));
    expect(current()).toHaveValue("");
    expect(current()).toHaveFocus();
    expect(fresh()).toHaveValue(NEW);
    expect(getAuthorization()).toBe("tok-a");
    expect(useUserStore.getState().user?.id).toBe("u1");
    expect(router.state.location.pathname).toBe("/user-setting/profile");
    expect(screen.queryByText("Session expired")).toBeNull();
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    // The submit button stays usable for another attempt.
    expect(submit()).not.toHaveAttribute("aria-disabled");
  });

  it.each([
    [429, 429, "Too many attempts. Wait a few minutes, then try again."],
    [503, 503, "The service is unavailable right now. Try again in a moment."],
    [500, -1, "Something went wrong. Try again."],
  ])("a %i is shown as a translated sentence and keeps the session", async (status, code, text) => {
    changeResponder = (config) => failure(config, status, code, "x");
    await ready();
    const user = await fill(OLD, NEW);
    await user.click(submit());
    expect(await screen.findByTestId("alert-password-error")).toHaveTextContent(text);
    expect(getAuthorization()).toBe("tok-a");
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it("on success purges the session locally, lands on a bare /login and toasts 'Password changed' only", async () => {
    const { router, client } = await ready();
    client.setQueryData(["other"], 1);
    const user = await fill(OLD, NEW);
    await user.click(submit());
    const login = await screen.findByTestId("login-page");
    expect(login).toHaveTextContent(/^\/login$/);
    expect(router.state.location.search).toBe("");
    expect(getAuthorization()).toBeNull();
    expect(useUserStore.getState().user).toBeNull();
    expect(client.getQueryData(["other"])).toBeUndefined();
    const toast = await screen.findByText("Password changed");
    expect(toast).toBeInTheDocument();
    expect(screen.getByText("Sign in with your new password.")).toBeInTheDocument();
    expect(screen.queryByText("Session expired")).toBeNull();
    expect(document.querySelectorAll("[data-sonner-toast]")).toHaveLength(1);
  });

  it("the 401 interceptor path does not fire a second toast: the server has already invalidated the token and nothing re-requests with it", async () => {
    const { client } = await ready();
    const user = await fill(OLD, NEW);
    const infoBefore = calls.filter((c) => c.url === "/v1/user/info").length;
    // From the moment the change is accepted the old token is dead on the server.
    changeResponder = (config) => {
      infoStatus = 401;
      return done(config, 200, { code: 0, message: "", data: null });
    };
    await user.click(submit());
    await screen.findByText("Password changed");
    await screen.findByTestId("login-page");
    expect(calls.filter((c) => c.url === "/v1/user/info")).toHaveLength(infoBefore);
    expect(client.getQueryCache().getAll()).toHaveLength(0);
    expect(screen.queryByText("Session expired")).toBeNull();
    expect(document.querySelectorAll("[data-sonner-toast]")).toHaveLength(1);
  });

  it("prevents a double submit while the request is pending", async () => {
    let release: () => void = () => undefined;
    changeResponder = (config) => new Promise((resolve) => (release = () => resolve(done(config, 200, { code: 0, message: "", data: null }))));
    await ready();
    const user = await fill(OLD, NEW);
    await user.click(submit());
    await waitUntil(() => changeCalls().length === 1, { describe: "first request" });
    expect(submit()).toHaveAttribute("aria-disabled", "true");
    expect(submit()).toHaveAttribute("aria-busy", "true");
    await user.click(submit());
    await user.type(confirm(), "{Enter}");
    expect(changeCalls()).toHaveLength(1);
    await act(async () => release());
    await screen.findByTestId("login-page");
    expect(changeCalls()).toHaveLength(1);
  });

  it("never keeps a password anywhere: not in storage, query or mutation caches, the DOM after success, or the console", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((level) => vi.spyOn(console, level).mockImplementation(() => undefined));
    changeResponder = (config) => failure(config, 400, 101, "current password is incorrect");
    const { client } = await ready();
    const user = await fill(OLD, NEW);
    await user.click(submit());
    await screen.findByTestId("alert-password-error");
    const dump = () => JSON.stringify([{ ...localStorage }, { ...sessionStorage }, client.getQueryCache().getAll().map((q) => q.queryKey), client.getMutationCache().getAll().length]);
    expect(dump()).not.toContain(OLD);
    expect(dump()).not.toContain(NEW);
    expect(client.getMutationCache().getAll()).toHaveLength(0);
    changeResponder = (config) => done(config, 200, { code: 0, message: "", data: null });
    await user.type(current(), OLD);
    await user.click(submit());
    await screen.findByTestId("login-page");
    expect(document.body.textContent).not.toContain(NEW);
    expect(dump()).not.toContain(NEW);
    for (const spy of spies) expect(JSON.stringify(spy.mock.calls)).not.toMatch(new RegExp(`${OLD}|${NEW}`));
  });

  it("starts with every field hidden, and the toggles reveal and re-hide them", async () => {
    await ready();
    const toggles = card().getAllByTestId("password-toggle");
    await userEvent.click(toggles[1]!);
    expect(fresh()).toHaveAttribute("type", "text");
    expect(current()).toHaveAttribute("type", "password");
    await userEvent.click(toggles[1]!);
    expect(fresh()).toHaveAttribute("type", "password");
  });
});
