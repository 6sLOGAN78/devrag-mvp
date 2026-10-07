import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { http, registerNavigate, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, setAuthorization } from "@/utils/authorization";
import ForgotPasswordPage from "./index";

const originalAdapter = http.defaults.adapter;
const FORGOT = "/api/v1/auth/password/forgot/otp";
const VERIFY = "/api/v1/auth/password/forgot/otp/verify";
const RESET = "/api/v1/auth/password/reset";
const EMAIL = "ada@example.test";
const CODE = "482913";
const TICKET = "ticket-secret-value-0123456789abcdef";
const NEW_PASSWORD = "brand-new-pass-0042";

type Reply = { status: number; body?: unknown; headers?: Record<string, string>; network?: boolean; hold?: Promise<void> };
const ok = (data: unknown = null): Reply => ({ status: 200, body: { code: 0, message: "", data } });
const bad = (message: string, status = 400): Reply => ({ status, body: { code: 101, message, data: null } });

let calls: InternalAxiosRequestConfig[] = [];
let forgotReply: Reply | (() => Reply);
let verifyReply: Reply | (() => Reply);
let resetReply: Reply | (() => Reply);

const pick = (reply: Reply | (() => Reply)): Reply => (typeof reply === "function" ? reply() : reply);

async function respond(config: InternalAxiosRequestConfig, reply: Reply) {
  if (reply.hold) await reply.hold;
  if (reply.network) throw new AxiosError("Network Error", "ERR_NETWORK", config);
  const response = { data: reply.body, status: reply.status, statusText: String(reply.status), headers: new AxiosHeaders(reply.headers), config } as never;
  if (reply.status >= 400) throw new AxiosError(`status ${reply.status}`, "ERR_BAD_RESPONSE", config, null, response);
  return response;
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  if (config.url === FORGOT) return respond(config, pick(forgotReply));
  if (config.url === VERIFY) return respond(config, pick(verifyReply));
  if (config.url === RESET) return respond(config, pick(resetReply));
  throw new AxiosError("Network Error", "ERR_NETWORK", config);
};

const callsTo = (url: string) => calls.filter((c) => c.url === url);
const bodyOf = (config: InternalAxiosRequestConfig | undefined) => JSON.parse(String(config?.data ?? "null")) as Record<string, unknown>;

function Probe() {
  const location = useLocation();
  return (
    <p data-testid="landed">
      {location.pathname}
      {location.search}
      {location.hash}
    </p>
  );
}

let client: QueryClient;

function renderPage() {
  const router = createMemoryRouter(
    [
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/login", element: <Probe /> },
    ],
    { initialEntries: ["/forgot-password"] },
  );
  client = new QueryClient();
  registerQueryClient(client);
  registerNavigate({ navigate: (to) => router.navigate(to, { replace: true }), currentPath: () => router.state.location.pathname });
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
  forgotReply = ok();
  verifyReply = ok({ reset_ticket: TICKET });
  resetReply = ok();
  useUserStore.getState().reset();
  http.defaults.adapter = adapter;
});

afterEach(() => {
  http.defaults.adapter = originalAdapter;
  registerNavigate(null);
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const title = (name: string) => screen.getByRole("heading", { level: 1, name });
const focused = (element: HTMLElement) => waitUntil(() => document.activeElement === element, { describe: "focus", timeout: 2000 });

async function submitEmail(user: ReturnType<typeof userEvent.setup>, email = EMAIL) {
  await user.clear(screen.getByTestId("field-email"));
  await user.type(screen.getByTestId("field-email"), email);
  await user.click(screen.getByTestId("forgot-submit"));
}

async function toStep2(user: ReturnType<typeof userEvent.setup>) {
  await submitEmail(user);
  await screen.findByTestId("forgot-step-2");
}

async function toStep3(user: ReturnType<typeof userEvent.setup>) {
  await toStep2(user);
  await user.type(screen.getByTestId("field-code"), CODE);
  await user.click(screen.getByTestId("forgot-submit"));
  await screen.findByTestId("forgot-step-3");
}

describe("step 1 (UI-SPEC Forgot password)", () => {
  it("renders the page, the step caption and title, the email field and the back link", async () => {
    renderPage();
    expect(await screen.findByTestId("forgot-page")).toBeInTheDocument();
    expect(screen.getByTestId("forgot-step-1")).toBeInTheDocument();
    expect(title("Reset your password")).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(screen.getByText("Enter your account email. We'll send a 6-digit code.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBe(screen.getByTestId("field-email"));
    expect(screen.getByTestId("forgot-submit")).toHaveTextContent("Send code");
    expect(screen.getByRole("link", { name: "Back to sign in" })).toHaveAttribute("href", "/login");
    expect(document.title).toBe("Reset password - devRag");
  });

  it("focuses the email field on first load", async () => {
    renderPage();
    await focused(screen.getByTestId("field-email"));
  });

  it("validates the email without sending anything", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByTestId("field-email"), "nope");
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByTestId("field-email")).toHaveAttribute("aria-invalid", "true");
    expect(calls).toHaveLength(0);
  });

  it("posts the normalised email anonymously, even when a token is stored, and advances to step 2", async () => {
    setAuthorization("tok-existing");
    const user = userEvent.setup();
    renderPage();
    await submitEmail(user, "  Ada@Example.test ");
    expect(await screen.findByTestId("forgot-step-2")).toBeInTheDocument();
    expect(callsTo(FORGOT)).toHaveLength(1);
    expect(bodyOf(callsTo(FORGOT)[0])).toEqual({ email: EMAIL });
    expect(callsTo(FORGOT)[0]!.headers.get("Authorization")).toBeFalsy();
    expect(screen.getByText(`If an account exists for ${EMAIL}, a 6-digit code is on its way. It expires in 10 minutes.`)).toBeInTheDocument();
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
    expect(getAuthorization()).toBe("tok-existing");
  });

  it("shows identical text and navigation for every 2xx response body (no account enumeration, D-07)", async () => {
    const texts: string[] = [];
    for (const reply of [ok(), ok({}), ok({ exists: true }), { status: 202, body: { code: 0, message: "queued", data: null } }, { status: 200, body: "" }] satisfies Reply[]) {
      forgotReply = reply;
      const user = userEvent.setup();
      const { unmount } = renderPage();
      await submitEmail(user);
      await screen.findByTestId("forgot-step-2");
      texts.push(screen.getByTestId("forgot-page").textContent ?? "");
      unmount();
    }
    expect(new Set(texts).size).toBe(1);
    expect(texts[0]).not.toMatch(/exist(s)? (and|but)|not found|no account|unknown/i);
  });

  it.each([
    ["429", { status: 429, body: { code: 429, message: "too many requests", data: null }, headers: { "Retry-After": "30" } } satisfies Reply, "Too many attempts. Wait a few minutes, then try again."],
    ["503", { status: 503, body: { code: 503, message: "service unavailable", data: null } } satisfies Reply, "The service is unavailable right now. Try again in a moment."],
    ["500", { status: 500, body: { code: 500, message: "internal error", data: null } } satisfies Reply, "Something went wrong. Try again."],
    ["network", { status: 0, network: true } satisfies Reply, "Something went wrong. Try again."],
  ])("stays on step 1 with a generic alert for %s, keeps the email, and raises no toast", async (_name, reply, message) => {
    forgotReply = reply;
    const user = userEvent.setup();
    renderPage();
    await submitEmail(user);
    expect(await screen.findByTestId("forgot-error")).toHaveTextContent(message);
    expect(screen.getByTestId("forgot-error")).toHaveAttribute("role", "alert");
    expect(screen.getByTestId("forgot-step-1")).toBeInTheDocument();
    expect(screen.getByTestId("field-email")).toHaveValue(EMAIL);
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });

  it("blocks a second submit while the first is pending", async () => {
    let release!: () => void;
    forgotReply = { status: 200, body: { code: 0, message: "", data: null }, hold: new Promise<void>((resolve) => (release = resolve)) };
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByTestId("field-email"), EMAIL);
    await user.click(screen.getByTestId("forgot-submit"));
    await user.click(screen.getByTestId("forgot-submit"));
    await user.type(screen.getByTestId("field-email"), "{Enter}");
    expect(callsTo(FORGOT)).toHaveLength(1);
    expect(screen.getByTestId("forgot-submit")).toHaveAttribute("aria-disabled", "true");
    release();
    await screen.findByTestId("forgot-step-2");
    expect(callsTo(FORGOT)).toHaveLength(1);
  });
});

describe("step 2: code and the resend countdown (D-06)", () => {
  it("moves focus to the step title and offers the code field with one-time-code semantics", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    await focused(title("Enter the code"));
    const code = screen.getByTestId("field-code");
    expect(screen.getByLabelText("6-digit code")).toBe(code);
    expect(code).toHaveAttribute("autocomplete", "one-time-code");
    expect(code).toHaveAttribute("inputmode", "numeric");
    expect(code).toHaveAttribute("maxlength", "6");
    expect(code).toHaveAttribute("placeholder", "123456");
    expect(screen.getByTestId("forgot-submit")).toHaveTextContent("Verify code");
    expect(screen.getByRole("link", { name: "Back to sign in" })).toBeInTheDocument();
  });

  it("keeps only digits when typing and accepts a pasted code with separators", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    const code = screen.getByTestId("field-code");
    await user.type(code, "12ab34-56");
    expect(code).toHaveValue("123456");
    await user.clear(code);
    await user.click(code);
    await user.paste("482 913");
    expect(code).toHaveValue(CODE);
    await user.clear(code);
    await user.paste("9876543210");
    expect(code).toHaveValue("987654");
  });

  it("rejects a short code locally without a request", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    await user.type(screen.getByTestId("field-code"), "123");
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByText("Enter the 6-digit code.")).toBeInTheDocument();
    expect(screen.getByTestId("field-code")).toHaveAttribute("aria-invalid", "true");
    expect(callsTo(VERIFY)).toHaveLength(0);
  });

  it("verifies the code anonymously with the email and moves to step 3", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep3(user);
    expect(callsTo(VERIFY)).toHaveLength(1);
    expect(bodyOf(callsTo(VERIFY)[0])).toEqual({ email: EMAIL, otp: CODE });
    expect(callsTo(VERIFY)[0]!.headers.get("Authorization")).toBeFalsy();
  });

  it("blocks a second verify while the first is pending", async () => {
    let release!: () => void;
    verifyReply = { status: 200, body: { code: 0, message: "", data: { reset_ticket: TICKET } }, hold: new Promise<void>((resolve) => (release = resolve)) };
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    await user.type(screen.getByTestId("field-code"), CODE);
    await user.click(screen.getByTestId("forgot-submit"));
    await user.click(screen.getByTestId("forgot-submit"));
    await user.type(screen.getByTestId("field-code"), "{Enter}");
    expect(callsTo(VERIFY)).toHaveLength(1);
    release();
    await screen.findByTestId("forgot-step-3");
  });

  it("shows the server message for a wrong code, falls back to the pinned copy, and stays on step 2", async () => {
    verifyReply = bad("That code is incorrect or has expired.");
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    await user.type(screen.getByTestId("field-code"), CODE);
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByTestId("forgot-error")).toHaveTextContent("That code is incorrect or has expired.");
    expect(screen.getByTestId("forgot-step-2")).toBeInTheDocument();
    // empty and over-long server messages are not shown
    verifyReply = bad("");
    await user.click(screen.getByTestId("forgot-submit"));
    await waitUntil(() => callsTo(VERIFY).length === 2, { describe: "second verify" });
    expect(await screen.findByTestId("forgot-error")).toHaveTextContent("That code is incorrect or has expired.");
    verifyReply = bad("x".repeat(161));
    await user.click(screen.getByTestId("forgot-submit"));
    await waitUntil(() => callsTo(VERIFY).length === 3, { describe: "third verify" });
    expect(screen.getByTestId("forgot-error")).toHaveTextContent("That code is incorrect or has expired.");
    expect(screen.getByTestId("forgot-error")).not.toHaveTextContent("xxxxxxxx");
  });

  it("returns to step 1 with the email kept after the fifth wrong attempt and not before", async () => {
    verifyReply = bad("That code is incorrect or has expired.");
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    for (let attempt = 1; attempt <= 4; attempt += 1) {
      await user.clear(screen.getByTestId("field-code"));
      await user.type(screen.getByTestId("field-code"), "000000");
      await user.click(screen.getByTestId("forgot-submit"));
      await waitUntil(() => callsTo(VERIFY).length === attempt, { describe: `verify ${attempt}` });
      expect(await screen.findByTestId("forgot-step-2")).toBeInTheDocument();
    }
    await user.clear(screen.getByTestId("field-code"));
    await user.type(screen.getByTestId("field-code"), "000000");
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByTestId("forgot-step-1")).toBeInTheDocument();
    expect(callsTo(VERIFY)).toHaveLength(5);
    expect(screen.getByTestId("field-email")).toHaveValue(EMAIL);
    expect(screen.getByTestId("forgot-error")).toHaveTextContent("That code is incorrect or has expired.");
    await focused(title("Reset your password"));
    expect(screen.queryByTestId("field-code")).toBeNull();
  });

  it("does not count a throttled or failed verify as a wrong attempt", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    for (const reply of [{ status: 429, body: { code: 429, message: "too many requests", data: null } }, { status: 503, body: { code: 503, message: "x", data: null } }, { status: 0, network: true }] satisfies Reply[]) {
      verifyReply = reply;
      for (let i = 0; i < 2; i += 1) {
        const before = callsTo(VERIFY).length;
        await user.clear(screen.getByTestId("field-code"));
        await user.type(screen.getByTestId("field-code"), "000000");
        await user.click(screen.getByTestId("forgot-submit"));
        await waitUntil(() => callsTo(VERIFY).length === before + 1, { describe: "verify" });
        await screen.findByTestId("forgot-error");
      }
    }
    expect(screen.getByTestId("forgot-step-2")).toBeInTheDocument();
  });
});

describe("resend countdown (fake timers)", () => {
  beforeEach(() => {
    // Only the interval and the clock are faked, so user-event and wait-until keep working on real timers.
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
  });

  const tick = (ms: number) =>
    act(() => {
      vi.advanceTimersByTime(ms);
    });
  const resend = () => screen.getByTestId("forgot-resend");

  it("starts at 60 seconds, counts down, and enables the resend button at zero", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    expect(resend()).toBeDisabled();
    expect(resend()).toHaveTextContent("Send a new code in 60s");
    tick(1000);
    expect(resend()).toHaveTextContent("Send a new code in 59s");
    tick(29_000);
    expect(resend()).toHaveTextContent("Send a new code in 30s");
    tick(30_000);
    expect(resend()).toBeEnabled();
    expect(resend()).toHaveTextContent("Send a new code");
    expect(resend()).not.toHaveTextContent("in ");
  });

  it("sends a new code and restarts the countdown from 60", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    tick(60_000);
    await user.click(resend());
    await waitUntil(() => callsTo(FORGOT).length === 2, { describe: "second send" });
    expect(bodyOf(callsTo(FORGOT)[1])).toEqual({ email: EMAIL });
    expect(await screen.findByText("A new code is on its way.")).toBeInTheDocument();
    expect(resend()).toBeDisabled();
    expect(resend()).toHaveTextContent("Send a new code in 60s");
  });

  it("restarts from Retry-After on a 429 and shows the generic throttle message", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    tick(60_000);
    forgotReply = { status: 429, body: { code: 429, message: "too many requests", data: null }, headers: { "Retry-After": "42" } };
    await user.click(resend());
    expect(await screen.findByTestId("forgot-error")).toHaveTextContent("Too many attempts. Wait a few minutes, then try again.");
    expect(resend()).toHaveTextContent("Send a new code in 42s");
    tick(42_000);
    expect(resend()).toBeEnabled();
  });

  it.each([
    ["a non-numeric value", "soon", 60],
    ["an HTTP date", "Wed, 21 Oct 2026 07:28:00 GMT", 60],
    ["a negative value", "-5", 60],
    ["zero", "0", 1],
    ["a huge value", "99999", 600],
  ])("restarts the countdown from the clamped value for Retry-After of %s", async (_name, header, expected) => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    tick(60_000);
    forgotReply = { status: 429, body: { code: 429, message: "too many requests", data: null }, headers: { "Retry-After": header } };
    await user.click(resend());
    await screen.findByTestId("forgot-error");
    expect(resend()).toHaveTextContent(`Send a new code in ${expected}s`);
  });

  it("does not send while the countdown runs", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    await user.click(resend());
    expect(callsTo(FORGOT)).toHaveLength(1);
  });

  it("shows a generic alert on a failed resend and keeps the code field", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    await user.type(screen.getByTestId("field-code"), "123");
    tick(60_000);
    forgotReply = { status: 503, body: { code: 503, message: "service unavailable", data: null } };
    await user.click(resend());
    expect(await screen.findByTestId("forgot-error")).toHaveTextContent("The service is unavailable right now. Try again in a moment.");
    expect(screen.getByTestId("field-code")).toHaveValue("123");
  });

  it("gives a fresh set of five attempts after a new code is sent", async () => {
    verifyReply = bad("That code is incorrect or has expired.");
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    for (let attempt = 1; attempt <= 4; attempt += 1) {
      await user.clear(screen.getByTestId("field-code"));
      await user.type(screen.getByTestId("field-code"), "000000");
      await user.click(screen.getByTestId("forgot-submit"));
      await waitUntil(() => callsTo(VERIFY).length === attempt, { describe: `verify ${attempt}` });
    }
    tick(60_000);
    await user.click(resend());
    await screen.findByText("A new code is on its way.");
    await user.clear(screen.getByTestId("field-code"));
    await user.type(screen.getByTestId("field-code"), "000000");
    await user.click(screen.getByTestId("forgot-submit"));
    await waitUntil(() => callsTo(VERIFY).length === 5, { describe: "fifth verify" });
    expect(screen.getByTestId("forgot-step-2")).toBeInTheDocument();
  });

  it("cleans up its timer when the page unmounts", async () => {
    const user = userEvent.setup();
    const view = renderPage();
    await toStep2(user);
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stops ticking once the button is enabled", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep2(user);
    tick(60_000);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("step 3: new password (D-02, D-08)", () => {
  it("moves focus to the step title, notes the sign-out, and has one password field with a toggle and no confirmation", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep3(user);
    await focused(title("Choose a new password"));
    expect(screen.getByText("Step 3 of 3")).toBeInTheDocument();
    expect(screen.getByText("You'll be signed out on every device.")).toBeInTheDocument();
    expect(screen.getByText("At least 8 characters.")).toBeInTheDocument();
    const field = screen.getByLabelText("New password");
    expect(field).toBe(screen.getByTestId("field-password"));
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getAllByTestId("password-toggle")).toHaveLength(1);
    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(1);
    expect(screen.queryByLabelText(/confirm/i)).toBeNull();
    expect(screen.getByTestId("forgot-submit")).toHaveTextContent("Reset password");
    expect(screen.getByRole("link", { name: "Back to sign in" })).toBeInTheDocument();
    await user.click(screen.getByTestId("password-toggle"));
    expect(field).toHaveAttribute("type", "text");
  });

  it("enforces 8 to 128 characters without a request", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep3(user);
    await user.type(screen.getByTestId("field-password"), "a".repeat(7));
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(screen.getByTestId("field-password")).toHaveAttribute("aria-invalid", "true");
    await user.clear(screen.getByTestId("field-password"));
    await user.click(screen.getByTestId("field-password"));
    await user.paste("a".repeat(129));
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByText("Use 128 characters or fewer.")).toBeInTheDocument();
    expect(callsTo(RESET)).toHaveLength(0);
  });

  it("resets with the ticket anonymously, purges any local session, creates none, and goes to /login with a toast", async () => {
    setAuthorization("tok-existing");
    useUserStore.getState().setUser({ id: "u1", nickname: "Ada", email: EMAIL, avatar: "", language: "English", colorSchema: "Bright", tenantId: "t1", tenantName: "w", role: "owner", isSuperuser: false });
    const user = userEvent.setup();
    const { router } = renderPage();
    await toStep3(user);
    await user.type(screen.getByTestId("field-password"), NEW_PASSWORD);
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByTestId("landed")).toHaveTextContent("/login");
    expect(router.state.location.search).toBe("");
    expect(callsTo(RESET)).toHaveLength(1);
    expect(bodyOf(callsTo(RESET)[0])).toEqual({ email: EMAIL, reset_ticket: TICKET, new_password: NEW_PASSWORD });
    expect(callsTo(RESET)[0]!.headers.get("Authorization")).toBeFalsy();
    expect(getAuthorization()).toBeNull();
    expect(useUserStore.getState().user).toBeNull();
    expect(await screen.findByText("Password reset")).toBeInTheDocument();
    expect(screen.getByText("Sign in with your new password.")).toBeInTheDocument();
    expect(screen.queryByText("Session expired")).toBeNull();
  });

  it("creates no session when none existed", async () => {
    const user = userEvent.setup();
    renderPage();
    await toStep3(user);
    await user.type(screen.getByTestId("field-password"), NEW_PASSWORD);
    await user.click(screen.getByTestId("forgot-submit"));
    await screen.findByTestId("landed");
    expect(getAuthorization()).toBeNull();
    expect(useUserStore.getState().user).toBeNull();
  });

  it("blocks a second reset while the first is pending", async () => {
    let release!: () => void;
    resetReply = { status: 200, body: { code: 0, message: "", data: null }, hold: new Promise<void>((resolve) => (release = resolve)) };
    const user = userEvent.setup();
    renderPage();
    await toStep3(user);
    await user.type(screen.getByTestId("field-password"), NEW_PASSWORD);
    await user.click(screen.getByTestId("forgot-submit"));
    await user.click(screen.getByTestId("forgot-submit"));
    await user.type(screen.getByTestId("field-password"), "{Enter}");
    expect(callsTo(RESET)).toHaveLength(1);
    release();
    await screen.findByTestId("landed");
    expect(callsTo(RESET)).toHaveLength(1);
  });

  it("returns to step 1 with the email kept and the server message when the ticket is refused", async () => {
    resetReply = bad("This reset session is invalid or has expired. Request a new code.");
    const user = userEvent.setup();
    renderPage();
    await toStep3(user);
    await user.type(screen.getByTestId("field-password"), NEW_PASSWORD);
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByTestId("forgot-step-1")).toBeInTheDocument();
    expect(screen.getByTestId("field-email")).toHaveValue(EMAIL);
    expect(screen.getByTestId("forgot-error")).toHaveTextContent("This reset session is invalid or has expired. Request a new code.");
    expect(getAuthorization()).toBeNull();
  });

  it.each([
    ["429", { status: 429, body: { code: 429, message: "too many requests", data: null } } satisfies Reply, "Too many attempts. Wait a few minutes, then try again."],
    ["503", { status: 503, body: { code: 503, message: "x", data: null } } satisfies Reply, "The service is unavailable right now. Try again in a moment."],
    ["500", { status: 500, body: { code: 500, message: "boom", data: null } } satisfies Reply, "Something went wrong. Try again."],
  ])("shows a generic alert for %s, stays on step 3 and keeps the typed password for a retry", async (_name, reply, message) => {
    resetReply = reply;
    const user = userEvent.setup();
    renderPage();
    await toStep3(user);
    await user.type(screen.getByTestId("field-password"), NEW_PASSWORD);
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByTestId("forgot-error")).toHaveTextContent(message);
    expect(screen.getByTestId("forgot-step-3")).toBeInTheDocument();
    expect(screen.getByTestId("field-password")).toHaveValue(NEW_PASSWORD);
    resetReply = ok();
    await user.click(screen.getByTestId("forgot-submit"));
    expect(await screen.findByTestId("landed")).toBeInTheDocument();
  });
});

describe("secrets stay in component memory (T-02-85)", () => {
  it("never reaches the URL, storage, query or mutation cache, or the console", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((level) => vi.spyOn(console, level).mockImplementation(() => undefined));
    const user = userEvent.setup();
    const { router } = renderPage();
    const seen: string[] = [];
    const record = () => {
      const { pathname, search, hash } = router.state.location;
      seen.push(`${pathname}${search}${hash}`, JSON.stringify({ ...localStorage }), JSON.stringify({ ...sessionStorage }), JSON.stringify(client.getQueryCache().getAll().map((q) => q.queryKey)));
      expect(client.getQueryCache().getAll()).toHaveLength(0);
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    };
    await submitEmail(user);
    await screen.findByTestId("forgot-step-2");
    record();
    await user.type(screen.getByTestId("field-code"), CODE);
    record();
    await user.click(screen.getByTestId("forgot-submit"));
    await screen.findByTestId("forgot-step-3");
    record();
    await user.type(screen.getByTestId("field-password"), NEW_PASSWORD);
    record();
    await user.click(screen.getByTestId("forgot-submit"));
    await screen.findByTestId("landed");
    record();
    const everything = [...seen, ...spies.flatMap((spy) => spy.mock.calls.map((args) => args.map(String).join(" ")))].join("\n");
    for (const secret of [CODE, TICKET, NEW_PASSWORD]) expect(everything).not.toContain(secret);
    expect(router.state.location.search).toBe("");
    expect(router.state.location.hash).toBe("");
    expect(router.state.location.state).toBeNull();
  });

  it("returns to an empty step 1 after a reload, whatever step the user was on", async () => {
    const user = userEvent.setup();
    const first = renderPage();
    await toStep3(user);
    first.unmount();
    renderPage();
    expect(await screen.findByTestId("forgot-step-1")).toBeInTheDocument();
    expect(screen.getByTestId("field-email")).toHaveValue("");
    expect(screen.queryByTestId("field-code")).toBeNull();
    expect(screen.queryByTestId("field-password")).toBeNull();
  });
});

describe("source hygiene", () => {
  it("renders messages as text, never as HTML", async () => {
    verifyReply = bad("<img src=x onerror=alert(1)>");
    const user = userEvent.setup();
    renderPage();
    await submitEmail(user, "ada@example.test");
    await screen.findByTestId("forgot-step-2");
    await user.type(screen.getByTestId("field-code"), CODE);
    await user.click(screen.getByTestId("forgot-submit"));
    const alert = await screen.findByTestId("forgot-error");
    expect(alert.querySelector("img")).toBeNull();
    expect(alert).toHaveTextContent("<img src=x onerror=alert(1)>");
  });
});
