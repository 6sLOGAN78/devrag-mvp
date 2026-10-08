import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { http, registerNavigate, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, setAuthorization } from "@/utils/authorization";
import LoginPage from "./index";

const originalAdapter = http.defaults.adapter;
const PASSWORD = "correct-horse-battery";
const WRONG = "wrong-pass-0001";
const PINNED = "Email or password is incorrect";

const userDto = {
  id: "u1",
  nickname: "Ada",
  email: "ada@example.test",
  avatar: "",
  language: "English",
  color_schema: "Bright",
  tenant_id: "t1",
  tenant_name: "Ada's workspace",
  role: "owner",
  is_superuser: false,
};

type Reply = { status: number; body?: unknown; network?: boolean; hold?: Promise<void> };
let calls: InternalAxiosRequestConfig[] = [];
let configReply: Reply;
let loginReply: Reply;
let registerReply: Reply;
let infoReply: Reply;

const ok = (data: unknown): Reply => ({ status: 200, body: { code: 0, message: "", data } });
const loginOk = ok({ token: "tok-new", user: { id: "u1" }, tenant_id: "t1", role: "owner" });

async function respond(config: InternalAxiosRequestConfig, reply: Reply) {
  if (reply.hold) await reply.hold;
  if (reply.network) throw new AxiosError("Network Error", "ERR_NETWORK", config);
  const response = { data: reply.body, status: reply.status, statusText: String(reply.status), headers: new AxiosHeaders(), config } as never;
  if (reply.status >= 400) throw new AxiosError(`status ${reply.status}`, "ERR_BAD_RESPONSE", config, null, response);
  return response;
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  if (config.url === "/api/v1/system/config") return respond(config, configReply);
  if (config.url === "/api/v1/auth/login") return respond(config, loginReply);
  if (config.url === "/api/v1/users") return respond(config, registerReply);
  if (config.url === "/v1/user/info") return respond(config, infoReply);
  throw new AxiosError("Network Error", "ERR_NETWORK", config);
};

const callsTo = (url: string) => calls.filter((c) => c.url === url);
const bodyOf = (config: InternalAxiosRequestConfig | undefined) => JSON.parse(String(config?.data ?? "null")) as Record<string, unknown>;

function Probe({ id }: { id: string }) {
  const location = useLocation();
  return (
    <p data-testid={id}>
      {location.pathname}
      {location.search}
    </p>
  );
}

let client: QueryClient;

function renderAt(entry = "/login") {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/home", element: <Probe id="landed" /> },
      { path: "/system-status", element: <Probe id="landed" /> },
      { path: "/evil.test", element: <Probe id="landed" /> },
      { path: "*", element: <Probe id="landed" /> },
    ],
    { initialEntries: [entry] },
  );
  client = new QueryClient();
  registerQueryClient(client);
  registerNavigate({
    navigate: (to) => router.navigate(to, { replace: true }),
    currentPath: () => `${router.state.location.pathname}${router.state.location.search}`,
  });
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
  return Object.assign(view, { router });
}

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});

beforeEach(() => {
  calls = [];
  configReply = ok({ engine: "go", api_version: "v1", service: "devrag", register_enabled: true });
  loginReply = loginOk;
  registerReply = ok({ id: "u1", email: "ada@example.test", nickname: "Ada" });
  infoReply = ok(userDto);
  useUserStore.getState().reset();
  http.defaults.adapter = adapter;
});

afterEach(() => {
  http.defaults.adapter = originalAdapter;
  registerNavigate(null);
  vi.restoreAllMocks();
  sessionStorage.clear();
});

async function fillLogin(user: ReturnType<typeof userEvent.setup>, email = "  Ada@Example.test ", password = PASSWORD) {
  await user.type(screen.getByTestId("field-email"), email);
  await user.type(screen.getByTestId("field-password"), password);
}

describe("sign-in rendering (UI-06)", () => {
  it("renders the page, form, fields, toggle and submit with their test ids", async () => {
    renderAt();
    expect(await screen.findByTestId("login-page")).toBeInTheDocument();
    expect(screen.getByTestId("login-form")).toBeInTheDocument();
    expect(screen.getByTestId("field-email")).toBeInTheDocument();
    expect(screen.getByTestId("field-password")).toBeInTheDocument();
    expect(screen.getByTestId("password-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("login-submit")).toHaveTextContent("Sign in");
    expect(screen.queryByTestId("register-form")).toBeNull();
    expect(screen.getByRole("heading", { level: 1, name: "Sign in to devRag" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute("href", "/forgot-password");
  });

  it("binds labels to inputs and uses the right autocomplete values", () => {
    renderAt();
    const email = screen.getByLabelText("Email");
    expect(email).toBe(screen.getByTestId("field-email"));
    expect(email).toHaveAttribute("autocomplete", "username");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("placeholder", "name@example.com");
    const password = screen.getByLabelText("Password");
    expect(password).toBe(screen.getByTestId("field-password"));
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
  });

  it("focuses the email field on mount", async () => {
    renderAt();
    await waitUntil(() => screen.getByTestId("field-email") === document.activeElement, { describe: "email focus" });
  });

  it("offers the sign-up switch only after the config reports registration on", async () => {
    renderAt();
    expect(screen.queryByTestId("mode-switch")).toBeNull();
    expect(await screen.findByTestId("mode-switch")).toHaveTextContent("Create one");
    expect(screen.getByText("No account yet?")).toBeInTheDocument();
  });

  it.each([
    ["registration is off", () => (configReply = ok({ register_enabled: false }))],
    ["the config request fails", () => (configReply = { status: 500, body: { code: 500, message: "boom", data: null } })],
    ["the config response is malformed", () => (configReply = ok({}))],
  ])("renders no sign-up switch when %s (fail closed)", async (_name, arrange) => {
    arrange();
    renderAt();
    await waitUntil(() => callsTo("/api/v1/system/config").length > 0, { describe: "config request" });
    await waitUntil(() => client.getQueryState(["system", "config"])?.fetchStatus === "idle", { describe: "config settled" });
    expect(screen.queryByTestId("mode-switch")).toBeNull();
    expect(screen.queryByText("No account yet?")).toBeNull();
    expect(screen.getByTestId("login-form")).toBeInTheDocument();
  });

  it("renders no sign-up switch while the config is still loading", () => {
    configReply = { status: 200, body: { code: 0, message: "", data: { register_enabled: true } }, hold: new Promise(() => undefined) };
    renderAt();
    expect(screen.queryByTestId("mode-switch")).toBeNull();
    expect(screen.getByTestId("login-form")).toBeInTheDocument();
  });
});

describe("sign-up rendering and the registration switch (D-01)", () => {
  it("renders the register form for ?mode=register when registration is on", async () => {
    renderAt("/login?mode=register");
    expect(await screen.findByTestId("register-form")).toBeInTheDocument();
    expect(screen.queryByTestId("login-form")).toBeNull();
    expect(screen.getByRole("heading", { level: 1, name: "Create your account" })).toBeInTheDocument();
    expect(screen.getByTestId("field-nickname")).toHaveAttribute("autocomplete", "nickname");
    expect(screen.getByTestId("field-email")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByTestId("field-password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByTestId("register-submit")).toHaveTextContent("Create account");
    expect(screen.getByText("At least 8 characters.")).toBeInTheDocument();
    expect(screen.getByTestId("mode-switch")).toHaveTextContent("Sign in");
    expect(screen.getByText("Already have an account?")).toBeInTheDocument();
    await waitUntil(() => screen.getByTestId("field-nickname") === document.activeElement, { describe: "nickname focus" });
  });

  it("shows sign-in plus the caption and no switch for ?mode=register when registration is off", async () => {
    configReply = ok({ register_enabled: false });
    renderAt("/login?mode=register");
    expect(await screen.findByText("New accounts are turned off on this server.")).toBeInTheDocument();
    expect(screen.getByTestId("login-form")).toBeInTheDocument();
    expect(screen.queryByTestId("register-form")).toBeNull();
    expect(screen.queryByTestId("field-nickname")).toBeNull();
    expect(screen.queryByTestId("mode-switch")).toBeNull();
  });

  it("never sends a registration request when registration is off, even for a deep link", async () => {
    configReply = ok({ register_enabled: false });
    renderAt("/login?mode=register");
    await screen.findByText("New accounts are turned off on this server.");
    expect(callsTo("/api/v1/users")).toHaveLength(0);
  });

  it("switches modes through the URL, keeps next, clears the form and moves focus to the card title", async () => {
    const user = userEvent.setup();
    const { router } = renderAt("/login?next=%2Fsystem-status");
    await user.type(screen.getByTestId("field-email"), "keep@example.test");
    await user.click(await screen.findByTestId("mode-switch"));
    expect(router.state.location.search).toContain("mode=register");
    expect(router.state.location.search).toContain("next=%2Fsystem-status");
    expect(await screen.findByTestId("register-form")).toBeInTheDocument();
    expect(screen.getByTestId("field-email")).toHaveValue("");
    await waitUntil(() => document.activeElement === screen.getByRole("heading", { level: 1, name: "Create your account" }), { describe: "title focus" });
    await user.click(screen.getByTestId("mode-switch"));
    expect(router.state.location.search).not.toContain("mode=");
    expect(router.state.location.search).toContain("next=%2Fsystem-status");
    expect(await screen.findByTestId("login-form")).toBeInTheDocument();
  });
});

describe("password field", () => {
  it("is a real toggle button with an accessible name that swaps the type", async () => {
    const user = userEvent.setup();
    renderAt();
    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toBe(screen.getByTestId("password-toggle"));
    expect(toggle).toHaveAttribute("type", "button");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await user.type(screen.getByTestId("field-password"), "abc");
    await user.click(toggle);
    expect(screen.getByTestId("field-password")).toHaveAttribute("type", "text");
    expect(screen.getByTestId("field-password")).toHaveValue("abc");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(screen.getByTestId("field-password")).toHaveAttribute("type", "password");
  });

  it("is operable from the keyboard", async () => {
    const user = userEvent.setup();
    renderAt();
    await user.click(screen.getByTestId("field-password"));
    await user.tab();
    expect(screen.getByTestId("password-toggle")).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("field-password")).toHaveAttribute("type", "text");
  });
});

describe("client validation mirrors the server and announces errors", () => {
  it("blocks an empty sign-in, flags both fields, focuses the first and sends nothing", async () => {
    const user = userEvent.setup();
    renderAt();
    await user.click(screen.getByTestId("login-submit"));
    const email = screen.getByTestId("field-email");
    const password = screen.getByTestId("field-password");
    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAttribute("aria-invalid", "true");
    const described = email.getAttribute("aria-describedby") ?? "";
    expect(described).not.toBe("");
    const message = document.getElementById(described.split(" ")[0]!);
    expect(message).toHaveTextContent("Enter your email address.");
    expect(message).toHaveAttribute("role", "alert");
    expect(email).toHaveFocus();
    expect(callsTo("/api/v1/auth/login")).toHaveLength(0);
  });

  it("rejects a malformed email without a request", async () => {
    const user = userEvent.setup();
    renderAt();
    await fillLogin(user, "not-an-email");
    await user.click(screen.getByTestId("login-submit"));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(callsTo("/api/v1/auth/login")).toHaveLength(0);
  });

  it("sign-up enforces nickname, email and password 8 to 128", async () => {
    const user = userEvent.setup();
    renderAt("/login?mode=register");
    await screen.findByTestId("register-form");
    await user.type(screen.getByTestId("field-nickname"), "Ada");
    await user.type(screen.getByTestId("field-email"), "ada@example.test");
    await user.type(screen.getByTestId("field-password"), "1234567");
    await user.click(screen.getByTestId("register-submit"));
    expect(await screen.findByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(callsTo("/api/v1/users")).toHaveLength(0);
    await user.type(screen.getByTestId("field-password"), "8");
    await waitUntil(() => screen.queryByText("Use at least 8 characters.") === null, { describe: "min error cleared" });
  });

  it("sign-up shows the max error at 129 characters", async () => {
    const user = userEvent.setup();
    renderAt("/login?mode=register");
    await screen.findByTestId("register-form");
    await user.type(screen.getByTestId("field-nickname"), "Ada");
    await user.type(screen.getByTestId("field-email"), "ada@example.test");
    await user.click(screen.getByTestId("field-password"));
    await user.paste("a".repeat(129));
    await user.click(screen.getByTestId("register-submit"));
    expect(await screen.findByText("Use 128 characters or fewer.")).toBeInTheDocument();
    expect(callsTo("/api/v1/users")).toHaveLength(0);
  });
});

describe("signing in", () => {
  it("posts the normalised credentials without a stale token, stores the token, loads the user and lands on /home", async () => {
    const user = userEvent.setup();
    const { router } = renderAt();
    await fillLogin(user);
    await user.click(screen.getByTestId("login-submit"));
    expect(await screen.findByTestId("landed")).toHaveTextContent("/home");
    const post = callsTo("/api/v1/auth/login")[0];
    expect(post?.method).toBe("post");
    expect(bodyOf(post)).toEqual({ email: "ada@example.test", password: PASSWORD });
    expect(post?.silent).toBe(true);
    expect(getAuthorization()).toBe("tok-new");
    expect(useUserStore.getState().user?.nickname).toBe("Ada");
    expect(callsTo("/v1/user/info")).toHaveLength(1);
    expect(router.state.location.pathname).toBe("/home");
  });

  it("never attaches a stored token to the login request", async () => {
    setAuthorization("stale-token");
    infoReply = { status: 0, network: true };
    const user = userEvent.setup();
    renderAt();
    await screen.findByTestId("login-form");
    expect(getAuthorization()).toBe("stale-token");
    infoReply = ok(userDto);
    await fillLogin(user);
    await user.click(screen.getByTestId("login-submit"));
    await screen.findByTestId("landed");
    const post = callsTo("/api/v1/auth/login")[0];
    expect(post?.headers.get("Authorization")).toBeFalsy();
    expect(post?.sentToken).toBeNull();
  });

  it.each([
    ["/system-status?tab=1", "/system-status?tab=1"],
    ["//evil.test/x", "/home"],
    ["/\\evil.test", "/home"],
    ["https://evil.test/", "/home"],
    ["javascript:alert(1)", "/home"],
    ["", "/home"],
  ])("honours next=%j only when it is a same-origin path (lands on %s)", async (next, expected) => {
    const user = userEvent.setup();
    const { router } = renderAt(`/login?next=${encodeURIComponent(next)}`);
    await fillLogin(user);
    await user.click(screen.getByTestId("login-submit"));
    await screen.findByTestId("landed");
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe(expected);
  });

  it("shows exactly the pinned message for a 401, never the server text, with no toast, no purge and no redirect", async () => {
    loginReply = { status: 401, body: { code: 401, message: "Email or password is incorrect (server)", data: null } };
    setAuthorization("keep-me");
    infoReply = { status: 500, body: { code: 500, message: "boom", data: null } };
    const user = userEvent.setup();
    const { router } = renderAt();
    await screen.findByTestId("login-form");
    await fillLogin(user, "ada@example.test", WRONG);
    await user.click(screen.getByTestId("login-submit"));
    const alert = await screen.findByTestId("login-error");
    expect(alert).toHaveTextContent(PINNED);
    expect(alert.textContent).toBe(PINNED);
    expect(alert).toHaveAttribute("role", "alert");
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    expect(router.state.location.pathname).toBe("/login");
    expect(getAuthorization()).toBe("keep-me");
  });

  it("uses the same pinned message for an unknown email, a 400 envelope and an envelope error inside HTTP 200", async () => {
    const user = userEvent.setup();
    renderAt();
    await fillLogin(user, "nobody@example.test", WRONG);
    for (const reply of [
      { status: 400, body: { code: 101, message: "invalid request", data: null } },
      { status: 200, body: { code: 401, message: "no such user", data: null } },
    ] satisfies Reply[]) {
      loginReply = reply;
      await user.click(screen.getByTestId("login-submit"));
      await waitUntil(() => screen.queryByTestId("login-error")?.textContent === PINNED, { describe: "pinned message" });
      await user.type(screen.getByTestId("field-password"), WRONG);
    }
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it("keeps the email, clears and focuses the password and hides it again after a failure", async () => {
    loginReply = { status: 401, body: { code: 401, message: "x", data: null } };
    const user = userEvent.setup();
    renderAt();
    await fillLogin(user, "ada@example.test", WRONG);
    await user.click(screen.getByTestId("password-toggle"));
    expect(screen.getByTestId("field-password")).toHaveAttribute("type", "text");
    await user.click(screen.getByTestId("login-submit"));
    await screen.findByTestId("login-error");
    expect(screen.getByTestId("field-email")).toHaveValue("ada@example.test");
    expect(screen.getByTestId("field-password")).toHaveValue("");
    expect(screen.getByTestId("field-password")).toHaveAttribute("type", "password");
    await waitUntil(() => screen.getByTestId("field-password") === document.activeElement, { describe: "password focus" });
    expect(getAuthorization()).toBeNull();
  });

  it("gives rate limiting its own message and leaves the form usable", async () => {
    loginReply = { status: 429, body: { code: 400, message: "too many requests", data: null } };
    const user = userEvent.setup();
    renderAt();
    await fillLogin(user);
    await user.click(screen.getByTestId("login-submit"));
    const alert = await screen.findByTestId("login-error");
    expect(alert).toHaveTextContent("Too many attempts. Wait a few minutes, then try again.");
    expect(alert).not.toHaveTextContent(PINNED);
    expect(screen.getByTestId("login-submit")).not.toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("field-email")).toHaveValue("Ada@Example.test");
  });

  it("gives an unavailable service its own message", async () => {
    loginReply = { status: 503, body: { code: 503, message: "service unavailable", data: null } };
    const user = userEvent.setup();
    renderAt();
    await fillLogin(user);
    await user.click(screen.getByTestId("login-submit"));
    expect(await screen.findByTestId("login-error")).toHaveTextContent("The service is unavailable right now. Try again in a moment.");
    expect(screen.getByTestId("login-error")).not.toHaveTextContent(PINNED);
  });

  it("does not claim the password is wrong when the server cannot be reached", async () => {
    loginReply = { status: 0, network: true };
    const user = userEvent.setup();
    renderAt();
    await fillLogin(user);
    await user.click(screen.getByTestId("login-submit"));
    expect(await screen.findByTestId("login-error")).toHaveTextContent("Something went wrong. Try again.");
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it("prevents a double submit while pending and tells assistive technology", async () => {
    let release: () => void = () => undefined;
    loginReply = { ...loginOk, hold: new Promise<void>((resolve) => (release = resolve)) };
    const user = userEvent.setup();
    renderAt();
    await fillLogin(user);
    const submit = screen.getByTestId("login-submit");
    await user.click(submit);
    await waitUntil(() => submit.getAttribute("aria-disabled") === "true", { describe: "pending state" });
    expect(submit).toHaveAttribute("aria-busy", "true");
    await user.click(submit);
    await user.type(screen.getByTestId("field-password"), "{Enter}");
    expect(within(screen.getByTestId("login-form")).getByRole("status")).toHaveTextContent("Signing in");
    expect(callsTo("/api/v1/auth/login")).toHaveLength(1);
    await act(async () => release());
    await screen.findByTestId("landed");
    expect(callsTo("/api/v1/auth/login")).toHaveLength(1);
  });
});

describe("registering", () => {
  async function fillRegister(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByTestId("field-nickname"), "  Ada  ");
    await user.type(screen.getByTestId("field-email"), "Ada@Example.test");
    await user.type(screen.getByTestId("field-password"), PASSWORD);
  }

  it("creates the account, signs in with the same credentials, loads the user and lands on /home", async () => {
    const user = userEvent.setup();
    renderAt("/login?mode=register");
    await screen.findByTestId("register-form");
    await fillRegister(user);
    await user.click(screen.getByTestId("register-submit"));
    expect(await screen.findByTestId("landed")).toHaveTextContent("/home");
    expect(bodyOf(callsTo("/api/v1/users")[0])).toEqual({ email: "ada@example.test", password: PASSWORD, nickname: "Ada" });
    expect(callsTo("/api/v1/users")[0]?.silent).toBe(true);
    expect(bodyOf(callsTo("/api/v1/auth/login")[0])).toEqual({ email: "ada@example.test", password: PASSWORD });
    expect(getAuthorization()).toBe("tok-new");
    expect(useUserStore.getState().user?.id).toBe("u1");
  });

  it("when the account was created but the automatic sign-in fails, moves to the sign-in form with the email kept and says so (IN-F03)", async () => {
    loginReply = { status: 503, body: { code: 503, message: "service unavailable", data: null } };
    const user = userEvent.setup();
    renderAt("/login?mode=register");
    await screen.findByTestId("register-form");
    await fillRegister(user);
    await user.click(screen.getByTestId("register-submit"));
    expect(await screen.findByTestId("login-form")).toBeInTheDocument();
    expect(screen.queryByTestId("register-form")).toBeNull();
    expect(screen.getByTestId("login-notice")).toHaveTextContent("Account created. Sign in to continue.");
    expect(screen.getByTestId("field-email")).toHaveValue("ada@example.test");
    expect(screen.getByTestId("field-password")).toHaveValue("");
    expect(screen.queryByTestId("login-error")).toBeNull();
    expect(getAuthorization()).toBeNull();

    loginReply = loginOk;
    await user.type(screen.getByTestId("field-password"), PASSWORD);
    await user.click(screen.getByTestId("login-submit"));
    expect(await screen.findByTestId("landed")).toHaveTextContent("/home");
    expect(callsTo("/api/v1/users")).toHaveLength(1);
  });

  it("honours a safe next after registering and ignores an unsafe one", async () => {
    const user = userEvent.setup();
    const { router } = renderAt(`/login?mode=register&next=${encodeURIComponent("//evil.test")}`);
    await screen.findByTestId("register-form");
    await fillRegister(user);
    await user.click(screen.getByTestId("register-submit"));
    await screen.findByTestId("landed");
    expect(router.state.location.pathname).toBe("/home");
  });

  it("shows the duplicate-email server message and keeps every field", async () => {
    registerReply = { status: 409, body: { code: 409, message: "email already registered", data: null } };
    const user = userEvent.setup();
    renderAt("/login?mode=register");
    await screen.findByTestId("register-form");
    await fillRegister(user);
    await user.click(screen.getByTestId("register-submit"));
    expect(await screen.findByTestId("login-error")).toHaveTextContent("email already registered");
    expect(screen.getByTestId("field-nickname")).toHaveValue("  Ada  ");
    expect(screen.getByTestId("field-email")).toHaveValue("Ada@Example.test");
    expect(screen.getByTestId("field-password")).toHaveValue(PASSWORD);
    expect(callsTo("/api/v1/auth/login")).toHaveLength(0);
    expect(getAuthorization()).toBeNull();
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it("does not swallow a server validation error, and replaces an oversized or empty one with the fallback", async () => {
    registerReply = { status: 400, body: { code: 101, message: "nickname contains characters that are not allowed", data: null } };
    const user = userEvent.setup();
    renderAt("/login?mode=register");
    await screen.findByTestId("register-form");
    await fillRegister(user);
    await user.click(screen.getByTestId("register-submit"));
    expect(await screen.findByTestId("login-error")).toHaveTextContent("nickname contains characters that are not allowed");
    registerReply = { status: 400, body: { code: 101, message: "x".repeat(161), data: null } };
    await user.click(screen.getByTestId("register-submit"));
    await waitUntil(() => screen.queryByTestId("login-error")?.textContent === "Something went wrong. Try again.", { describe: "fallback" });
  });

  it("explains rate limiting and an unavailable service in our own words", async () => {
    registerReply = { status: 429, body: { code: 400, message: "too many requests", data: null } };
    const user = userEvent.setup();
    renderAt("/login?mode=register");
    await screen.findByTestId("register-form");
    await fillRegister(user);
    await user.click(screen.getByTestId("register-submit"));
    expect(await screen.findByTestId("login-error")).toHaveTextContent("Too many attempts. Wait a few minutes, then try again.");
    registerReply = { status: 503, body: { code: 503, message: "service unavailable", data: null } };
    await user.click(screen.getByTestId("register-submit"));
    await waitUntil(() => screen.queryByTestId("login-error")?.textContent?.startsWith("The service is unavailable") === true, { describe: "503 message" });
  });

  it("prevents a double submit while pending", async () => {
    let release: () => void = () => undefined;
    registerReply = { ...ok({ id: "u1" }), hold: new Promise<void>((resolve) => (release = resolve)) };
    const user = userEvent.setup();
    renderAt("/login?mode=register");
    await screen.findByTestId("register-form");
    await fillRegister(user);
    const submit = screen.getByTestId("register-submit");
    await user.click(submit);
    await waitUntil(() => submit.getAttribute("aria-disabled") === "true", { describe: "pending" });
    await user.click(submit);
    expect(within(screen.getByTestId("register-form")).getByRole("status")).toHaveTextContent("Creating your account");
    expect(callsTo("/api/v1/users")).toHaveLength(1);
    await act(async () => release());
    await screen.findByTestId("landed");
    expect(callsTo("/api/v1/users")).toHaveLength(1);
  });
});

describe("the password is never persisted or exposed", () => {
  it("is absent from storage, URL, query and mutation caches, stores, title and console after success and failure", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((level) => vi.spyOn(console, level).mockImplementation(() => undefined));
    const user = userEvent.setup();
    const { router } = renderAt();
    await fillLogin(user, "ada@example.test", WRONG);
    loginReply = { status: 401, body: { code: 401, message: "x", data: null } };
    await user.click(screen.getByTestId("login-submit"));
    await screen.findByTestId("login-error");
    await user.type(screen.getByTestId("field-password"), PASSWORD);
    loginReply = loginOk;
    await user.click(screen.getByTestId("login-submit"));
    await screen.findByTestId("landed");

    const everywhere = JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
      url: `${router.state.location.pathname}${router.state.location.search}${window.location.href}`,
      queries: client.getQueryCache().getAll().map((q) => ({ key: q.queryKey, state: q.state })),
      mutations: client.getMutationCache().getAll().map((m) => ({ key: m.options.mutationKey, state: m.state })),
      store: useUserStore.getState(),
      title: document.title,
      console: spies.map((spy) => spy.mock.calls),
    });
    expect(everywhere).not.toContain(PASSWORD);
    expect(everywhere).not.toContain(WRONG);
    expect(calls.map((c) => c.url)).not.toContain(undefined);
    for (const call of calls) expect(String(call.url)).not.toMatch(/password|pass=/i);
  });

  it("is not rendered into the DOM as text", async () => {
    const user = userEvent.setup();
    renderAt();
    await fillLogin(user);
    expect(document.body.textContent).not.toContain(PASSWORD);
  });
});

describe("already signed in", () => {
  it("redirects a visitor with a valid session straight to /home", async () => {
    setAuthorization("tok-valid");
    const { router } = renderAt();
    expect(await screen.findByTestId("landed")).toHaveTextContent("/home");
    expect(router.state.location.pathname).toBe("/home");
    expect(screen.queryByTestId("login-form")).toBeNull();
  });

  it("shows the form when the stored token is rejected, and leaves no token behind", async () => {
    setAuthorization("tok-revoked");
    infoReply = { status: 401, body: { code: 401, message: "revoked", data: null } };
    renderAt();
    expect(await screen.findByTestId("login-form")).toBeInTheDocument();
    expect(getAuthorization()).toBeNull();
  });

  it("shows the form when session recovery fails for a network reason", async () => {
    setAuthorization("tok-valid");
    infoReply = { status: 0, network: true };
    renderAt();
    expect(await screen.findByTestId("login-form")).toBeInTheDocument();
  });
});
