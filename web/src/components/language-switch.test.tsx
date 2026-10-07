import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { LanguageSwitch } from "@/components/language-switch";
import { Toaster } from "@/components/ui/sonner";
import i18n from "@/i18n";
import { LANG_KEY } from "@/i18n/language";
import { BareLayout } from "@/layouts/bare-layout";
import { http } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { setAuthorization } from "@/utils/authorization";

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

describe("LanguageSwitch", () => {
  it("is a labelled icon button that opens English and 中文, each in its own language", async () => {
    const user = userEvent.setup();
    render(<LanguageSwitch />);
    const trigger = screen.getByTestId("language-switch");
    expect(trigger).toBe(screen.getByRole("button", { name: "Change language" }));
    await user.click(trigger);
    const en = await screen.findByTestId("language-option-en");
    const zh = screen.getByTestId("language-option-zh");
    expect(en).toHaveTextContent("English");
    expect(zh).toHaveTextContent("中文");
    expect(en).toHaveAttribute("lang", "en");
    expect(zh).toHaveAttribute("lang", "zh");
    expect(within(en).getByTestId("language-current")).toBeInTheDocument();
    expect(within(zh).queryByTestId("language-current")).toBeNull();
  });

  it("applies the choice at once, sets <html lang>, persists it and shows no toast", async () => {
    const user = userEvent.setup();
    render(<LanguageSwitch />);
    await user.click(screen.getByTestId("language-switch"));
    await user.click(await screen.findByTestId("language-option-zh"));
    await waitUntil(() => i18n.language === "zh", { describe: "language zh" });
    expect(document.documentElement.lang).toBe("zh");
    expect(localStorage.getItem(LANG_KEY)).toBe("zh");
    expect(screen.getByTestId("language-switch")).toHaveAttribute("aria-label", "切换语言");
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });
});

describe("BareLayout corner cluster", () => {
  it("lets a signed-out visitor change language and theme", () => {
    const router = createMemoryRouter([{ element: <BareLayout />, children: [{ path: "*", element: <p>page body</p> }] }]);
    render(<RouterProvider router={router} />);
    expect(screen.getByTestId("language-switch")).toBeInTheDocument();
    expect(screen.getByTestId("theme-toggle")).toBeInTheDocument();
    expect(screen.getByText("page body")).toBeInTheDocument();
  });

  it("stays blank when a guard supplies its own children", () => {
    render(<BareLayout>{null}</BareLayout>);
    expect(screen.queryByTestId("language-switch")).toBeNull();
  });
});

describe("LanguageSwitch server write (UI-42, D-23)", () => {
  const originalAdapter = http.defaults.adapter;
  let calls: InternalAxiosRequestConfig[] = [];
  let mode: "ok" | "500" | "network" | "400" = "ok";
  const adapter: AxiosAdapter = (config) => {
    calls.push(config);
    const done = (status: number, data: unknown) => ({ data, status, statusText: String(status), headers: new AxiosHeaders(), config }) as never;
    if (mode === "ok") return Promise.resolve(done(200, { code: 0, message: "", data: { id: "u1" } }));
    if (mode === "network") return Promise.reject(new AxiosError("Network Error", "ERR_NETWORK", config));
    const status = mode === "500" ? 500 : 400;
    return Promise.reject(new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config, null, done(status, { code: status === 500 ? 500 : 101, message: "nope", data: null })));
  };
  const USER = { id: "u1", nickname: "Ada", email: "a@example.test", avatar: "", language: "en", colorSchema: "Bright", tenantId: "t1", tenantName: "W", role: "owner", isSuperuser: false };

  function setup(signedIn: boolean) {
    calls = [];
    mode = "ok";
    http.defaults.adapter = adapter;
    if (signedIn) {
      useUserStore.getState().setUser(USER);
      setAuthorization("tok-a");
    }
    return render(
      <>
        <LanguageSwitch />
        <Toaster />
      </>,
    );
  }
  async function choose(code: "en" | "zh") {
    await userEvent.click(screen.getByTestId("language-switch"));
    await userEvent.click(await screen.findByTestId(`language-option-${code}`));
  }
  afterEach(() => {
    http.defaults.adapter = originalAdapter;
    useUserStore.getState().reset();
  });

  it("when signed in, sends only language, silently, and records it on the user in the store", async () => {
    setup(true);
    await choose("zh");
    await waitUntil(() => calls.length === 1, { describe: "language write request" });
    expect(calls[0]!.url).toBe("/v1/user/setting");
    expect(calls[0]!.method).toBe("post");
    expect(JSON.parse(String(calls[0]!.data))).toEqual({ language: "zh" });
    expect(calls[0]!.silent).toBe(true);
    expect(new AxiosHeaders(calls[0]!.headers as never).get("Authorization")).toBe("Bearer tok-a");
    await waitUntil(() => useUserStore.getState().user?.language === "zh", { describe: "store language" });
    expect(i18n.language).toBe("zh");
    expect(localStorage.getItem(LANG_KEY)).toBe("zh");
  });

  it.each([["a 500", "500" as const], ["a 400", "400" as const], ["a network error", "network" as const]])(
    "shows no toast and keeps the choice when the write fails with %s",
    async (_name, failure) => {
      setup(true);
      mode = failure;
      await choose("zh");
      await waitUntil(() => calls.length === 1, { describe: "language write request" });
      await waitUntil(() => i18n.language === "zh", { describe: "language applied" });
      expect(document.querySelector("[data-sonner-toast]")).toBeNull();
      expect(localStorage.getItem(LANG_KEY)).toBe("zh");
      expect(document.documentElement.lang).toBe("zh");
      expect(useUserStore.getState().user?.language).toBe("en");
    },
  );

  it("when signed out, only changes local state and sends nothing", async () => {
    setup(false);
    await choose("zh");
    await waitUntil(() => i18n.language === "zh", { describe: "language applied" });
    expect(calls).toEqual([]);
    expect(localStorage.getItem(LANG_KEY)).toBe("zh");
  });

  it("does not break when storage is blocked: the language still applies for the session", async () => {
    setup(true);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation((key: string) => {
      if (key === LANG_KEY) throw new DOMException("blocked", "SecurityError");
    });
    await choose("zh");
    await waitUntil(() => i18n.language === "zh", { describe: "language applied" });
    expect(document.documentElement.lang).toBe("zh");
    vi.restoreAllMocks();
  });
});
