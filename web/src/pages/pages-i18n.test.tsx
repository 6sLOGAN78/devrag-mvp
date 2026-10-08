import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { goHealthPath } from "@/constants/api-paths";
import i18n, { setLanguage } from "@/i18n";
import { http } from "@/services/http";
import { setAuthorization } from "@/utils/authorization";
import NotFoundPage from "./not-found";
import RouteError from "./route-error";
import SystemStatusPage from "./system-status";

/** The exact English text of every key moved off constants/copy.ts, asserted through the real i18n instance. */
const ENGLISH: Record<string, string> = {
  "notFound.display": "404",
  "notFound.heading": "Page not found",
  "notFound.pageTitle": "Page not found - devRag",
  "notFound.body": "This page doesn't exist or isn't available in this version.",
  "notFound.action": "Go to home",
  "renderError.heading": "Something went wrong",
  "renderError.body": "This page failed to load. Reload to try again.",
  "renderError.action": "Reload page",
  "status.title": "System status",
  "status.pageTitle": "System status - devRag",
  "status.refresh": "Refresh status",
  "status.loading": "Checking services",
  "status.sourceLabel": "X-API-Source",
  "status.healthy": "Healthy",
  "status.degraded": "Degraded",
  "status.unreachable": "Unreachable",
  "status.down": "Down",
  "status.ok": "OK",
  "status.goApi": "Go API",
  "status.pythonApi": "Python API",
  "status.errorNoun": "service status",
  "status.dependencies.database": "Database",
  "status.dependencies.redis": "Redis",
  "status.dependencies.storage": "Storage",
  "status.dependencies.doc_store": "Doc store",
  "toast.apiError.title": "Request failed",
  "toast.apiError.fallback": "The server rejected the request. Try again.",
  "toast.serverError.title": "Server error",
  "toast.serverError.description": "The server hit a problem. Try again in a moment.",
  "toast.network.title": "Can't reach the server",
  "toast.network.description": "Check your connection and try again.",
  "toast.timeout.title": "Request timed out",
  "toast.timeout.description": "The server took too long to respond. Try again.",
  "toast.session.title": "Session expired",
  "toast.session.description": "Sign in again to continue.",
};

describe("migrated Phase 1 copy (UI-42)", () => {
  it.each(Object.entries(ENGLISH))("%s reads the specified English", (key, text) => {
    expect(i18n.exists(key)).toBe(true);
    expect(i18n.t(key)).toBe(text);
  });

  it("interpolates the updated time and the elapsed milliseconds", () => {
    expect(i18n.t("status.updated", { time: "10:00" })).toBe("Updated 10:00");
    expect(i18n.t("status.elapsedMs", { ms: 3 })).toBe("3 ms");
  });
});

describe("pages render in both languages", () => {
  it("Not Found renders English then Chinese through useTranslation", async () => {
    const view = render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to home" })).toHaveAttribute("href", "/home");
    expect(document.title).toBe("Page not found - devRag");
    view.unmount();
    await act(async () => {
      await setLanguage("zh");
    });
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: i18n.t("notFound.heading") }).textContent).not.toBe("Page not found");
    expect(screen.getByRole("link").textContent).not.toBe("Go to home");
  });

  it("the render error page uses the keys", async () => {
    render(<RouteError />);
    expect(screen.getByRole("heading", { level: 1, name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByText("This page failed to load. Reload to try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload page" })).toBeInTheDocument();
  });
});

describe("system status page language switch", () => {
  const original = http.defaults.adapter;
  const adapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
    const body =
      config.url === goHealthPath
        ? { code: 0, message: "", data: { status: "ok", engine: "go", checks: { database: { status: "ok", elapsed_ms: 3 } } } }
        : { code: 0, message: "", data: { status: "ok", engine: "python", checks: { redis: { status: "down", elapsed_ms: 9 } } } };
    const headers = new AxiosHeaders();
    if (config.url === undefined) throw new AxiosError("x");
    return { data: body, status: 200, statusText: "", headers, config };
  };
  beforeEach(() => {
    http.defaults.adapter = adapter;
  });
  afterEach(() => {
    http.defaults.adapter = original;
  });

  it("renders the labels, dependency names, ms unit and page title in Chinese", async () => {
    await act(async () => {
      await setLanguage("zh");
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SystemStatusPage />
      </QueryClientProvider>,
    );
    const goCard = await screen.findByTestId("status-card-go");
    expect(await within(goCard).findByTestId("status-card-go-badge")).toHaveTextContent(i18n.t("status.healthy"));
    expect(i18n.t("status.healthy")).not.toBe("Healthy");
    expect(within(goCard).getByTestId("status-dependency-database")).toHaveTextContent(i18n.t("status.dependencies.database"));
    expect(within(goCard).getByTestId("status-dependency-database")).toHaveTextContent(i18n.t("status.elapsedMs", { ms: 3 }));
    expect(document.title).toBe(i18n.t("status.pageTitle"));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(i18n.t("status.title"));
  });
});

describe("http toasts follow the language (instance used directly, not a hook)", () => {
  const original = http.defaults.adapter;
  afterEach(() => {
    http.defaults.adapter = original;
  });

  it("shows the Chinese network toast after a language switch", async () => {
    http.defaults.adapter = () => Promise.reject(new AxiosError("Network Error", "ERR_NETWORK"));
    await act(async () => {
      await setLanguage("zh");
    });
    render(<Toaster />);
    await expect(http.get("/api/v1/anything")).rejects.toBeTruthy();
    const zhTitle = i18n.t("toast.network.title");
    expect(zhTitle).not.toBe("Can't reach the server");
    expect(await screen.findByText(zhTitle)).toBeInTheDocument();
    expect(await screen.findByText(i18n.t("toast.network.description"))).toBeInTheDocument();
  });

  it("shows the Chinese purge notice and keeps the token rule", async () => {
    setAuthorization("tok-1");
    http.defaults.adapter = (config) =>
      Promise.reject(
        new AxiosError("unauth", "ERR_BAD_REQUEST", config, null, { data: { code: 401, message: "", data: null }, status: 401, statusText: "", headers: new AxiosHeaders(), config }),
      );
    await act(async () => {
      await setLanguage("zh");
    });
    render(<Toaster />);
    await expect(http.get("/api/v1/anything")).rejects.toBeTruthy();
    expect(await screen.findByText(i18n.t("toast.session.description"))).toBeInTheDocument();
    expect(i18n.t("toast.session.description")).toBe("请重新登录以继续。");
  });
});
