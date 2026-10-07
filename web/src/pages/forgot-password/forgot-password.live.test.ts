import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { appendFileSync } from "node:fs";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { buildRoutes } from "@/routes";
import { useUserStore } from "@/stores/user-store";
import { deleteMailFor, extractCode, noMailFor, waitForMail } from "@/test/mail";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, removeAuthorization } from "@/utils/authorization";

// Runs against the real ingress (LIVE_BASE_URL) with the `mail` compose profile up (MAILPIT_URL, default
// http://127.0.0.1:8025): the real SPA page, the real HTTP client, the real Go endpoints and a real SMTP catcher.
// The code is read from the captured message, never from the cache or from logs. Throwaway accounts only.
const OLD_PASSWORD = "test-only-pass-0001";
const NEW_PASSWORD = "test-only-pass-0002";
const PINNED = "Email or password is incorrect";
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
const EMAIL = `webreset-${suffix}@example.test`;
const UNKNOWN = `webreset-nobody-${suffix}@example.test`;

/** The browser tier has no database access, so created e-mails go to LIVE_ACCOUNTS_FILE (when set) for removal afterwards. */
function recordAccount(email: string): void {
  const file = process.env.LIVE_ACCOUNTS_FILE;
  if (file) appendFileSync(file, `${email}\n`);
}

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(new URL(path, window.location.origin), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
  const envelope = (await response.json()) as Envelope<T>;
  if (envelope.code !== 0) throw new Error(`${path} returned envelope code ${envelope.code}`);
  return envelope.data;
}

async function loginToken(email: string, password: string): Promise<string> {
  return (await post<{ token: string }>("/api/v1/auth/login", { email, password })).token;
}

async function statusWithToken(token: string): Promise<number> {
  const response = await fetch(new URL("/v1/user/info", window.location.origin), { headers: { Authorization: `Bearer ${token}` } });
  return response.status;
}

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.scrollIntoView ??= () => undefined;
});
afterEach(() => {
  cleanup();
  removeAuthorization();
  useUserStore.getState().reset();
});
afterAll(async () => {
  await deleteMailFor(EMAIL);
  await deleteMailFor(UNKNOWN);
});

function loadApp(path: string) {
  useUserStore.getState().reset();
  const router = createMemoryRouter(buildRoutes(), { initialEntries: [path] });
  render(createElement(QueryClientProvider, { client: new QueryClient() }, createElement(RouterProvider, { router }), createElement(Toaster)));
  return router;
}

const field = (id: string) => screen.getByTestId(id);

describe("live password reset through the ingress and Mailpit", () => {
  let oldToken = "";

  it("waits for the ingress health route and the mail catcher", async () => {
    await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
    await waitUntil(async () => (await fetch(`${process.env.MAILPIT_URL ?? "http://127.0.0.1:8025"}/api/v1/info`)).ok, {
      describe: "the mail catcher (start the stack with the mail profile)",
      timeout: 60_000,
    });
  });

  it("registers an account through the API and holds a valid token", async () => {
    await post("/api/v1/users", { email: EMAIL, password: OLD_PASSWORD, nickname: `webreset-${suffix}` });
    recordAccount(EMAIL);
    oldToken = await loginToken(EMAIL, OLD_PASSWORD);
    expect(await statusWithToken(oldToken)).toBe(200);
  });

  it("takes an unknown email to step 2 like any other and no mail arrives for it", async () => {
    const user = userEvent.setup();
    loadApp("/forgot-password");
    await waitUntil(() => screen.queryByTestId("forgot-step-1"), { describe: "step 1" });
    await user.type(field("field-email"), UNKNOWN);
    await user.click(screen.getByTestId("forgot-submit"));
    await waitUntil(() => screen.queryByTestId("forgot-step-2"), { describe: "step 2 for an unknown email" });
    expect(await noMailFor(UNKNOWN)).toBe(true);
  });

  it("resets the password with the real emailed code, signs out every device and creates no session", async () => {
    const user = userEvent.setup();
    const router = loadApp("/forgot-password");
    await waitUntil(() => screen.queryByTestId("forgot-step-1"), { describe: "step 1" });
    await user.type(field("field-email"), EMAIL);
    await user.click(screen.getByTestId("forgot-submit"));
    await waitUntil(() => screen.queryByTestId("forgot-step-2"), { describe: "step 2" });

    const code = extractCode(await waitForMail(EMAIL));
    expect(code).toMatch(/^\d{6}$/);
    await user.type(field("field-code"), code);
    await user.click(screen.getByTestId("forgot-submit"));
    await waitUntil(() => screen.queryByTestId("forgot-step-3"), { describe: "step 3 after the code is accepted" });

    await user.type(field("field-password"), NEW_PASSWORD);
    await user.click(screen.getByTestId("forgot-submit"));
    await waitUntil(() => router.state.location.pathname === "/login", { describe: "navigation to /login after the reset" });
    expect(getAuthorization()).toBeNull();
    expect(router.state.location.search).toBe("");
    expect(document.body.textContent).not.toContain(NEW_PASSWORD);
    expect(document.body.textContent).not.toContain(code);
  });

  it("rejects the old token, refuses the old password with the pinned message and accepts the new password", async () => {
    expect(await statusWithToken(oldToken)).toBe(401);

    const user = userEvent.setup();
    const router = loadApp("/login");
    await waitUntil(() => screen.queryByTestId("login-form"), { describe: "the sign-in form" });
    await user.type(field("field-email"), EMAIL);
    await user.type(field("field-password"), OLD_PASSWORD);
    await user.click(screen.getByTestId("login-submit"));
    const alert = await waitUntil(() => screen.queryByTestId("login-error"), { describe: "the inline error for the old password" });
    expect(alert.textContent).toBe(PINNED);

    await user.type(field("field-password"), NEW_PASSWORD);
    await user.click(screen.getByTestId("login-submit"));
    await waitUntil(() => router.state.location.pathname === "/home", { describe: "signing in with the new password lands on /home" });
    expect(getAuthorization()).not.toBeNull();
  });
});
