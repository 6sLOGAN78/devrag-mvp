import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { appendFileSync } from "node:fs";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { buildRoutes } from "@/routes";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, removeAuthorization } from "@/utils/authorization";

// Runs against the real ingress (LIVE_BASE_URL, default http://127.0.0.1:8080): the real SPA routes, the real
// HTTP client and the real Go endpoints. Nothing is faked. The throwaway account is obviously fake and unique.
const PASSWORD = "test-only-pass-0001";
const PINNED = "Email or password is incorrect";
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
const EMAIL = `webauth-${suffix}@example.test`;
const NICKNAME = `webauth-${suffix}`;

/** The browser tier has no database access, so created e-mails go to LIVE_ACCOUNTS_FILE (when set) for removal by id afterwards. */
function recordAccount(email: string): void {
  const file = process.env.LIVE_ACCOUNTS_FILE;
  if (file) appendFileSync(file, `${email}\n`);
}

type Router = ReturnType<typeof createMemoryRouter>;

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

/** A fresh app instance, like a page load: new router, new query cache, empty user store. */
function loadApp(path: string): Router {
  useUserStore.getState().reset();
  const router = createMemoryRouter(buildRoutes(), { initialEntries: [path] });
  render(createElement(QueryClientProvider, { client: new QueryClient() }, createElement(RouterProvider, { router }), createElement(Toaster)));
  return router;
}

const heading = (name: string) => screen.queryByRole("heading", { level: 1, name });
const field = (id: string) => screen.getByTestId(id);

describe("live sign up, sign in and the guard through the ingress", () => {
  it("waits for the ingress health route", async () => {
    await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
  });

  it("registers in the SPA, is signed in with the same credentials and lands on /home", async () => {
    const user = userEvent.setup();
    const router = loadApp("/login?mode=register");
    await waitUntil(() => screen.queryByTestId("register-form"), { describe: "the register form (registration must be enabled on the stack)" });
    await user.type(field("field-nickname"), NICKNAME);
    await user.type(field("field-email"), EMAIL);
    await user.type(field("field-password"), PASSWORD);
    await user.click(screen.getByTestId("register-submit"));
    recordAccount(EMAIL);
    await waitUntil(() => router.state.location.pathname === "/home", { describe: "landing on /home after registration" });
    await waitUntil(() => heading(`Welcome, ${NICKNAME}`), { describe: "the welcome title" });
    expect(screen.getByTestId("stat-role")).toHaveTextContent("Owner");
    expect(getAuthorization()).not.toBeNull();
    expect(document.body.textContent).not.toContain(PASSWORD);
  });

  it("keeps the session across a reload", async () => {
    const user = userEvent.setup();
    const router = loadApp("/login?mode=register");
    await waitUntil(() => screen.queryByTestId("register-form"), { describe: "the register form" });
    // Register a second throwaway account only to obtain a stored token for the reload; its rows are removed by id like the first.
    const email = `webauth-r-${suffix}@example.test`;
    await user.type(field("field-nickname"), `${NICKNAME}-r`);
    await user.type(field("field-email"), email);
    await user.type(field("field-password"), PASSWORD);
    await user.click(screen.getByTestId("register-submit"));
    recordAccount(email);
    await waitUntil(() => router.state.location.pathname === "/home", { describe: "landing on /home" });
    cleanup();
    useUserStore.getState().reset();
    // Same storage, new app instance: the token alone recovers the session.
    const reloaded = loadApp("/home");
    await waitUntil(() => heading(`Welcome, ${NICKNAME}-r`), { describe: "the welcome title after a reload" });
    expect(reloaded.state.location.pathname).toBe("/home");
  });

  it("redirects to /login?next=%2Fhome once storage is cleared", async () => {
    const user = userEvent.setup();
    const router = loadApp("/login");
    await waitUntil(() => screen.queryByTestId("login-form"), { describe: "the sign-in form" });
    await user.type(field("field-email"), EMAIL);
    await user.type(field("field-password"), PASSWORD);
    await user.click(screen.getByTestId("login-submit"));
    await waitUntil(() => router.state.location.pathname === "/home", { describe: "signing in lands on /home" });
    cleanup();
    localStorage.clear();
    useUserStore.getState().reset();
    const guarded = loadApp("/home");
    await waitUntil(() => guarded.state.location.pathname === "/login", { describe: "the guard redirect" });
    expect(guarded.state.location.search).toBe("?next=%2Fhome");
    expect(screen.queryByTestId("layout-standard")).toBeNull();
  });

  it("shows exactly the pinned message for a wrong password and for an unknown email, with no toast", async () => {
    const user = userEvent.setup();
    loadApp("/login");
    await waitUntil(() => screen.queryByTestId("login-form"), { describe: "the sign-in form" });
    await user.type(field("field-email"), EMAIL);
    await user.type(field("field-password"), "not-the-password");
    await user.click(screen.getByTestId("login-submit"));
    const wrongPassword = await waitUntil(() => screen.queryByTestId("login-error"), { describe: "the inline error for a wrong password" });
    expect(wrongPassword.textContent).toBe(PINNED);
    expect(field("field-email")).toHaveValue(EMAIL);
    expect(field("field-password")).toHaveValue("");

    await user.clear(field("field-email"));
    await user.type(field("field-email"), `webauth-nobody-${suffix}@example.test`);
    await user.type(field("field-password"), PASSWORD);
    await user.click(screen.getByTestId("login-submit"));
    await waitUntil(() => screen.queryByTestId("login-error")?.textContent === PINNED && field("field-password").getAttribute("value") === "", {
      describe: "the same inline error for an unknown email",
    });
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    expect(getAuthorization()).toBeNull();
  });
});
