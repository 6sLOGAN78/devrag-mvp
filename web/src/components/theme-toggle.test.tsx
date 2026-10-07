import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeToggle } from "@/components/theme-toggle";
import { Toaster } from "@/components/ui/sonner";
import { http } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { setAuthorization } from "@/utils/authorization";
import { THEME_KEY } from "@/utils/theme";

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let fail = false;
const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  const done = (status: number, data: unknown) => ({ data, status, statusText: String(status), headers: new AxiosHeaders(), config }) as never;
  if (fail) return Promise.reject(new AxiosError("status 500", "ERR_BAD_RESPONSE", config, null, done(500, { code: 500, message: "boom", data: null })));
  return Promise.resolve(done(200, { code: 0, message: "", data: { id: "u1" } }));
};
const USER = { id: "u1", nickname: "Ada", email: "a@example.test", avatar: "", language: "en", colorSchema: "Bright", tenantId: "t1", tenantName: "W", role: "owner", isSuperuser: false };

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});
beforeEach(() => {
  calls = [];
  fail = false;
  http.defaults.adapter = adapter;
  document.documentElement.classList.remove("dark");
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
});

async function choose(name: "Light" | "Dark" | "System") {
  await userEvent.click(screen.getByTestId("theme-toggle"));
  await userEvent.click(await screen.findByRole("menuitem", { name }));
}
function setup(signedIn: boolean) {
  if (signedIn) {
    useUserStore.getState().setUser(USER);
    setAuthorization("tok-a");
  }
  render(
    <>
      <ThemeToggle />
      <Toaster />
    </>,
  );
}

describe("ThemeToggle (UI-43)", () => {
  it.each([
    ["Dark", "dark", "Dark"],
    ["Light", "light", "Bright"],
  ] as const)("choosing %s applies it, stores it and, when signed in, writes color_schema %s silently", async (name, stored, schema) => {
    setup(true);
    await choose(name);
    expect(localStorage.getItem(THEME_KEY)).toBe(stored);
    expect(document.documentElement.classList.contains("dark")).toBe(stored === "dark");
    await waitUntil(() => calls.length === 1, { describe: "colour schema write" });
    expect(calls[0]!.url).toBe("/v1/user/setting");
    expect(JSON.parse(String(calls[0]!.data))).toEqual({ color_schema: schema });
    expect(calls[0]!.silent).toBe(true);
    await waitUntil(() => useUserStore.getState().user?.colorSchema === schema, { describe: "store colour schema" });
  });

  it("System removes the stored choice and writes nothing to the server", async () => {
    setup(true);
    localStorage.setItem(THEME_KEY, "dark");
    await choose("System");
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
    expect(calls).toEqual([]);
  });

  it("when signed out, applies and stores the theme and sends nothing", async () => {
    setup(false);
    await choose("Dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(calls).toEqual([]);
  });

  it("shows no toast and keeps the theme when the server write fails", async () => {
    setup(true);
    fail = true;
    await choose("Dark");
    await waitUntil(() => calls.length === 1, { describe: "colour schema write" });
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
    expect(useUserStore.getState().user?.colorSchema).toBe("Bright");
  });
});
