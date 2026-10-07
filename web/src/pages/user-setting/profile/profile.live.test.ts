import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { appendFileSync } from "node:fs";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import i18n from "@/i18n";
import { LANG_KEY } from "@/i18n/language";
import { buildRoutes } from "@/routes";
import { registerNavigate, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, removeAuthorization, setAuthorization } from "@/utils/authorization";
import { THEME_KEY } from "@/utils/theme";

// Runs against the real ingress (LIVE_BASE_URL): the real SPA routes, the real HTTP client and the real Go
// endpoints. Only the browser's pixel work (decoding and drawing an image) is replaced, because jsdom has no
// canvas; the data URL it returns is a real 1x1 PNG, so the server's own avatar validation runs on it. Every
// account is its own, uniquely named, and recorded for removal by the runner (the browser tier has no database).
const OLD_SECRET = ["live", "old", "pass", "0001"].join("-");
const NEW_SECRET = ["live", "new", "pass", "0002"].join("-");
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
const PNG_1X1 =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}
interface InfoData {
  nickname: string;
  avatar: string;
  language: string;
  color_schema: string;
}
interface Account {
  email: string;
  nickname: string;
  token: string;
}

function recordAccount(email: string): void {
  const file = process.env.LIVE_ACCOUNTS_FILE;
  if (file) appendFileSync(file, `${email}\n`);
}

async function call<T>(path: string, init: { method?: string; token?: string; body?: unknown } = {}): Promise<{ status: number; envelope: Envelope<T> | null }> {
  const response = await fetch(new URL(path, window.location.origin), {
    method: init.method ?? "GET",
    headers: { "Content-Type": "application/json", ...(init.token ? { Authorization: `Bearer ${init.token}` } : {}) },
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

async function signIn(email: string, secret: string): Promise<{ status: number; token: string | null }> {
  const { status, envelope } = await call<{ token?: string }>("/api/v1/auth/login", { method: "POST", body: { email, password: secret } });
  return { status, token: envelope?.code === 0 ? (envelope.data?.token ?? null) : null };
}

/** A real account through the real endpoints. Its name carries the plan and a unique suffix so it is easy to find and remove. */
async function createAccount(tag: string): Promise<Account> {
  const email = `webprofile-${tag}-${suffix}@example.test`;
  const nickname = `webprofile-${tag}-${suffix}`;
  const created = await call("/api/v1/users", { method: "POST", body: { email, password: OLD_SECRET, nickname } });
  recordAccount(email);
  if (created.status !== 200 || created.envelope?.code !== 0) throw new Error(`registering ${tag} returned HTTP ${created.status}`);
  const login = await signIn(email, OLD_SECRET);
  if (login.token === null) throw new Error(`signing in ${tag} returned HTTP ${login.status}`);
  return { email, nickname, token: login.token };
}

async function info(token: string): Promise<InfoData> {
  const { envelope } = await call<InfoData>("/v1/user/info", { token });
  if (!envelope || envelope.code !== 0) throw new Error("GET /v1/user/info failed");
  return envelope.data;
}

type Router = ReturnType<typeof createMemoryRouter>;

/** A fresh app instance, like a page load: new router, new query cache, empty user store. The token in storage is all it has. */
function loadApp(path: string): Router {
  useUserStore.getState().reset();
  const router = createMemoryRouter(buildRoutes(), { initialEntries: [path] });
  const client = new QueryClient();
  registerQueryClient(client);
  registerNavigate({
    navigate: (to) => router.navigate(to, { replace: true }),
    currentPath: () => `${router.state.location.pathname}${router.state.location.search}`,
  });
  render(createElement(QueryClientProvider, { client }, createElement(RouterProvider, { router }), createElement(Toaster)));
  return router;
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
  document.documentElement.classList.remove("dark");
  vi.restoreAllMocks();
});

/** jsdom cannot decode or draw images; this stands in for the browser's pixel work only. */
function stubPixelWork(): void {
  class FakeImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    naturalWidth = 640;
    naturalHeight = 480;
    set src(_value: string) {
      queueMicrotask(() => this.onload?.());
    }
  }
  vi.stubGlobal("Image", FakeImage);
  URL.createObjectURL = () => "blob:live/avatar";
  URL.revokeObjectURL = () => undefined;
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => ({ drawImage: () => undefined, fillRect: () => undefined, fillStyle: "", imageSmoothingQuality: "low" }) as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockImplementation(() => PNG_1X1);
}

const page = () => screen.getByTestId("profile-page");
const nicknameField = () => within(page()).getByLabelText("Nickname");

describe("live profile, language, theme and password through the ingress", () => {
  it("waits for the ingress health route", async () => {
    await waitUntil(async () => (await fetch(new URL("/health", window.location.origin))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
  });

  it("redirects a signed-out visit of /user-setting/profile to /login with the encoded next", async () => {
    localStorage.clear();
    const router = loadApp("/user-setting/profile");
    await waitUntil(() => router.state.location.pathname === "/login", { describe: "the guard redirect" });
    expect(router.state.location.search).toBe("?next=%2Fuser-setting%2Fprofile");
    expect(screen.queryByTestId("layout-standard")).toBeNull();
    expect(screen.queryByTestId("profile-page")).toBeNull();
  });

  it("changes nickname and avatar through the SPA, updates the header at once and keeps both across a reload", async () => {
    stubPixelWork();
    const account = await createAccount("profile");
    setAuthorization(account.token);
    const user = userEvent.setup();
    loadApp("/user-setting/profile");
    await waitUntil(() => screen.queryByTestId("profile-form"), { describe: "the profile form" });
    expect(within(page()).getByLabelText("Email")).toHaveValue(account.email);
    expect(nicknameField()).toHaveValue(account.nickname);

    const renamed = `${account.nickname}-renamed`;
    await user.clear(nicknameField());
    await user.type(nicknameField(), renamed);
    await user.upload(screen.getByTestId("avatar-input"), new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3])], "me.png", { type: "image/png" }));
    await waitUntil(() => page().querySelector("img")?.getAttribute("src") === PNG_1X1, { describe: "the staged avatar preview" });
    // Nothing is saved until the form is submitted.
    expect((await info(account.token)).nickname).toBe(account.nickname);
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    await screen.findByText("Profile saved");

    const saved = await info(account.token);
    expect(saved.nickname).toBe(renamed);
    expect(saved.avatar).toBe(PNG_1X1);
    // The header avatar and menu follow the store without a reload.
    await waitUntil(() => screen.getByTestId("user-menu").querySelector("img")?.getAttribute("src") === PNG_1X1, { describe: "the header avatar" });
    await user.click(screen.getByTestId("user-menu"));
    expect(await screen.findByText(renamed)).toBeInTheDocument();
    await user.keyboard("{Escape}");

    cleanup();
    useUserStore.getState().reset();
    loadApp("/user-setting/profile");
    await waitUntil(() => screen.queryByTestId("profile-form"), { describe: "the profile form after a reload" });
    expect(nicknameField()).toHaveValue(renamed);
    expect(page().querySelector("img")).toHaveAttribute("src", PNG_1X1);
    expect(screen.getByTestId("avatar-remove")).toBeInTheDocument();
  });

  it("rejects an avatar the server refuses, with a message, and keeps the stored one", async () => {
    const account = await createAccount("badavatar");
    const refused = await call("/v1/user/setting", { method: "POST", token: account.token, body: { avatar: "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=" } });
    expect(refused.status).toBe(400);
    expect((await info(account.token)).avatar).toBe("");
  });

  it("writes language and theme to the profile best-effort, and applies user.language after sign-in when there is no local choice", async () => {
    const account = await createAccount("prefs");
    setAuthorization(account.token);
    const user = userEvent.setup();
    loadApp("/home");
    await waitUntil(() => screen.queryByTestId("home-page") && screen.queryByTestId("language-switch"), { describe: "the home page" });

    await user.click(screen.getByTestId("language-switch"));
    await user.click(await screen.findByTestId("language-option-zh"));
    await waitUntil(async () => (await info(account.token)).language === "zh", { describe: "user.language zh on the server" });
    expect(localStorage.getItem(LANG_KEY)).toBe("zh");
    expect(document.documentElement.lang).toBe("zh");

    await user.click(screen.getByTestId("theme-toggle"));
    await user.click(await screen.findByRole("menuitem", { name: i18n.t("theme.dark") }));
    await waitUntil(async () => (await info(account.token)).color_schema === "Dark", { describe: "color_schema Dark on the server" });
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();

    // A new browser: no local language or theme choice. The server values apply once the session is recovered.
    cleanup();
    localStorage.clear();
    setAuthorization(account.token);
    await i18n.changeLanguage("en");
    document.documentElement.classList.remove("dark");
    loadApp("/home");
    await waitUntil(() => screen.queryByTestId("home-page") && useUserStore.getState().user !== null, { describe: "session recovery" });
    await waitUntil(() => i18n.language === "zh", { describe: "user.language applied" });
    await waitUntil(() => document.documentElement.classList.contains("dark"), { describe: "server Dark theme applied" });
    expect(localStorage.getItem(LANG_KEY)).toBeNull();
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("keeps the session on a wrong current password, then changes it: back to /login, old token dead, new password works", async () => {
    const account = await createAccount("password");
    setAuthorization(account.token);
    const user = userEvent.setup();
    const router = loadApp("/user-setting/profile");
    await waitUntil(() => screen.queryByTestId("password-form"), { describe: "the password form" });
    const form = within(screen.getByTestId("password-form"));

    // Wrong current password: field error from the server message, still signed in.
    await user.type(form.getByLabelText("Current password"), "not-the-right-one");
    await user.type(form.getByLabelText("New password", { exact: true }), NEW_SECRET);
    await user.click(form.getByRole("button", { name: "Change password" }));
    const alert = await waitUntil(() => screen.queryByTestId("alert-password-error"), { describe: "the wrong-password alert" });
    expect(alert.textContent?.length).toBeGreaterThan(0);
    expect(form.getByLabelText("Current password")).toHaveAttribute("aria-invalid", "true");
    expect(router.state.location.pathname).toBe("/user-setting/profile");
    expect(getAuthorization()).toBe(account.token);
    expect((await call("/v1/user/info", { token: account.token })).status).toBe(200);
    expect(screen.queryByText("Session expired")).toBeNull();

    // The right current password.
    await user.type(form.getByLabelText("Current password"), OLD_SECRET);
    await user.click(form.getByRole("button", { name: "Change password" }));
    await waitUntil(() => router.state.location.pathname === "/login", { describe: "landing on /login after the change" });
    expect(router.state.location.search).toBe("");
    expect(getAuthorization()).toBeNull();
    await screen.findByText("Password changed");
    expect(screen.queryByText("Session expired")).toBeNull();
    expect(document.querySelectorAll("[data-sonner-toast]")).toHaveLength(1);

    // On the server: the old token is rejected, the old password no longer works, the new one does.
    const stale = await call("/v1/user/info", { token: account.token });
    expect(stale.status).toBe(401);
    expect((await signIn(account.email, OLD_SECRET)).token).toBeNull();
    expect((await signIn(account.email, NEW_SECRET)).token).not.toBeNull();
    expect(document.body.textContent).not.toContain(NEW_SECRET);
    expect(JSON.stringify({ ...localStorage })).not.toContain(NEW_SECRET);
  });
});
