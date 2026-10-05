import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { goHealthPath, pythonStatusPath } from "@/constants/api-paths";
import { http } from "@/services/http";
import { waitUntil } from "@/test/wait-until";
import SystemStatusPage from "./index";

type Probe = { status: string; elapsed_ms: number };
const ok = (ms = 3): Probe => ({ status: "ok", elapsed_ms: ms });
const down: Probe = { status: "down", elapsed_ms: 2000 };

const goOk = { status: "ok", engine: "go", checks: { database: ok(), redis: ok() } };
const pyOk = { status: "ok", engine: "python", checks: { database: ok(), redis: ok(), storage: ok(), doc_store: ok() } };
const pyDown = { status: "down", engine: "python", checks: { database: ok(), redis: down, storage: ok(), doc_store: ok() } };

interface Reply {
  status: number;
  body?: unknown;
  source?: string;
  network?: boolean;
}

let replies: Record<string, Reply>;
let calls: Record<string, number>;
const originalAdapter = http.defaults.adapter;

const adapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const url = config.url ?? "";
  calls[url] = (calls[url] ?? 0) + 1;
  const reply = replies[url];
  if (!reply || reply.network) throw new AxiosError("Network Error", "ERR_NETWORK", config);
  const headers = new AxiosHeaders();
  if (reply.source) headers.set("X-API-Source", reply.source);
  const response = { data: reply.body, status: reply.status, statusText: "", headers, config };
  if (reply.status >= 200 && reply.status < 300) return response;
  throw new AxiosError(`HTTP ${reply.status}`, "ERR_BAD_RESPONSE", config, null, response);
};

function envelope(data: unknown, code = 0, message = "") {
  return { code, message, data };
}

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <SystemStatusPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  calls = {};
  replies = {};
  http.defaults.adapter = adapter;
});

afterEach(() => {
  http.defaults.adapter = originalAdapter;
});

describe("SystemStatusPage", () => {
  it("shows loading skeletons with the Checking services caption first", () => {
    replies = {
      [goHealthPath]: { status: 200, body: envelope(goOk), source: "go" },
      [pythonStatusPath]: { status: 200, body: envelope(pyOk), source: "python" },
    };
    renderPage();
    expect(screen.getAllByText("Checking services")).toHaveLength(2);
    expect(screen.getByRole("heading", { level: 1, name: "System status" })).toBeInTheDocument();
  });

  it("renders both healthy cards with dependencies and the X-API-Source captions", async () => {
    replies = {
      [goHealthPath]: { status: 200, body: envelope(goOk), source: "go" },
      [pythonStatusPath]: { status: 200, body: envelope(pyOk), source: "python" },
    };
    renderPage();
    const goCard = await screen.findByTestId("status-card-go");
    const pyCard = screen.getByTestId("status-card-python");
    expect(await within(goCard).findByTestId("status-card-go-badge")).toHaveTextContent("Healthy");
    expect(await within(pyCard).findByTestId("status-card-python-badge")).toHaveTextContent("Healthy");
    expect(within(goCard).getByTestId("status-card-go-source")).toHaveTextContent("go");
    expect(within(pyCard).getByTestId("status-card-python-source")).toHaveTextContent("python");
    expect(within(goCard).getByTestId("status-dependency-database")).toHaveTextContent("OK");
    expect(within(goCard).queryByTestId("status-dependency-storage")).toBeNull();
    for (const name of ["database", "redis", "storage", "doc_store"]) {
      expect(within(pyCard).getByTestId(`status-dependency-${name}`)).toHaveTextContent("OK");
    }
    expect(within(pyCard).getByText(/^Updated /)).toBeInTheDocument();
    expect(document.title).toBe("System status - devRag");
  });

  it("keeps the dependency list for a 503 and marks the card Degraded", async () => {
    replies = {
      [goHealthPath]: { status: 200, body: envelope(goOk), source: "go" },
      [pythonStatusPath]: { status: 503, body: envelope(pyDown, 503, "service unavailable"), source: "python" },
    };
    renderPage();
    const pyCard = await screen.findByTestId("status-card-python");
    expect(await within(pyCard).findByTestId("status-card-python-badge")).toHaveTextContent("Degraded");
    expect(within(pyCard).getByTestId("status-dependency-redis")).toHaveTextContent("Down");
    expect(within(pyCard).getByTestId("status-dependency-database")).toHaveTextContent("OK");
  });

  it("isolates a network failure to one card", async () => {
    replies = {
      [goHealthPath]: { status: 200, body: envelope(goOk), source: "go" },
      [pythonStatusPath]: { status: 0, network: true },
    };
    renderPage();
    const goCard = await screen.findByTestId("status-card-go");
    const pyCard = screen.getByTestId("status-card-python");
    expect(await within(goCard).findByTestId("status-card-go-badge")).toHaveTextContent("Healthy");
    await waitUntil(() => within(pyCard).queryByTestId("error-state") !== null, { describe: "python error state", timeout: 8000 });
    expect(within(pyCard).getByTestId("status-card-python-badge")).toHaveTextContent("Unreachable");
    expect(within(pyCard).getByRole("heading", { name: "Couldn't load service status" })).toBeInTheDocument();
    expect(within(goCard).queryByTestId("error-state")).toBeNull();
    // retry: 1 means the failing request was attempted twice
    expect(calls[pythonStatusPath]).toBe(2);
  });

  it("refetches both engines when Refresh status is clicked", async () => {
    replies = {
      [goHealthPath]: { status: 200, body: envelope(goOk), source: "go" },
      [pythonStatusPath]: { status: 200, body: envelope(pyOk), source: "python" },
    };
    renderPage();
    await screen.findByTestId("status-card-go-badge");
    await screen.findByTestId("status-card-python-badge");
    expect(calls[goHealthPath]).toBe(1);
    await userEvent.click(screen.getByRole("button", { name: "Refresh status" }));
    await waitUntil(() => calls[goHealthPath] === 2 && calls[pythonStatusPath] === 2, { describe: "second request round" });
    expect(calls[goHealthPath]).toBe(2);
  });

  it("does not raise error toasts for failures (silent requests)", async () => {
    replies = {
      [goHealthPath]: { status: 0, network: true },
      [pythonStatusPath]: { status: 0, network: true },
    };
    renderPage();
    await waitUntil(() => screen.queryAllByTestId("error-state").length === 2, { describe: "both error states", timeout: 8000 });
    expect(document.querySelector("[data-sonner-toast]")).toBeNull();
  });
});
