import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/sonner";
import { http, purgeSession, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { setAuthorization } from "@/utils/authorization";
import ApiTokensPage from ".";
import { maskToken } from "./mask";

// Obviously fake token values; the middles are distinctive so a leak is easy to detect.
const T1 = "ragflow-FAKEONE-middle-secret-0000000000000000-aaa1";
const T2 = "ragflow-FAKETWO-middle-secret-1111111111111111-bbb2";
const T3 = "ragflow-FAKENEW-middle-secret-2222222222222222-ccc3";
const NOW = Date.UTC(2026, 9, 8, 12, 0, 0);

interface Row {
  token: string;
  beta: string;
  create_time: number;
}
const row = (token: string, create_time = NOW): Row => ({ token, beta: "0".repeat(32), create_time });

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let tokens: Row[] = [];
let handler: (config: InternalAxiosRequestConfig) => Promise<unknown> | unknown;

const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function failure(config: InternalAxiosRequestConfig, status: number, code: number, message: string, headers: Record<string, string> = {}) {
  const response = { data: { code, message, data: null }, status, statusText: String(status), headers: new AxiosHeaders(headers), config } as never;
  return Promise.reject(new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config, null, response));
}

/** The default server: a list, a create that prepends T3, and a delete that removes the addressed token. */
function defaultHandler(config: InternalAxiosRequestConfig): unknown {
  const method = String(config.method).toLowerCase();
  if (config.url === "/api/v1/system/tokens" && method === "get") return ok(config, tokens);
  if (config.url === "/api/v1/system/tokens" && method === "post") {
    const created = row(T3, NOW + 1000);
    tokens = [created, ...tokens];
    return ok(config, created);
  }
  if (config.url?.startsWith("/api/v1/system/tokens/") && method === "delete") {
    const id = decodeURIComponent(config.url.slice("/api/v1/system/tokens/".length));
    tokens = tokens.filter((t) => t.token !== id);
    return ok(config, null);
  }
  return failure(config, 404, 404, "not found");
}

const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  return Promise.resolve(handler(config)) as never;
};

const callsTo = (method: string) => calls.filter((c) => String(c.method).toLowerCase() === method && String(c.url).startsWith("/api/v1/system/tokens"));

let client: QueryClient;
function renderPage() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ApiTokensPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

const writeText = vi.fn();
function stubClipboard(impl: ((text: string) => Promise<void>) | "absent"): void {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: impl === "absent" ? undefined : { writeText: (text: string) => impl(text) },
  });
}
function newUser() {
  const user = userEvent.setup();
  stubClipboard(async (text) => void writeText(text));
  return user;
}

const rows = () => screen.getAllByTestId("token-row");
const rowFor = (tail: string) => rows().find((r) => within(r).queryAllByRole("button", { name: new RegExp(`ending ${tail}$`) }).length > 0)!;

beforeEach(() => {
  calls = [];
  tokens = [row(T1, NOW - 86_400_000), row(T2, NOW - 2 * 86_400_000)];
  handler = defaultHandler;
  writeText.mockReset();
  useUserStore.getState().reset();
  setAuthorization("tok-session");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  vi.useRealTimers();
});

describe("API tokens page structure (UI-35)", () => {
  it("makes the page title the first heading, sets the title and shows the intro and the Create token action", async () => {
    renderPage();
    const page = screen.getByTestId("tokens-page");
    expect(within(page).getByRole("heading", { level: 1, name: "API tokens" })).toBe(within(page).getAllByRole("heading")[0]);
    expect(document.title).toBe("API tokens - devRag");
    expect(within(page).getByText(/Send it as a Bearer token in the Authorization header/)).toBeInTheDocument();
    await screen.findByTestId("tokens-table");
    expect(within(page).getAllByRole("button", { name: "Create token" })).toHaveLength(1);
  });

  it("renders a semantic table with an sr-only caption, scoped column headers and one row per token", async () => {
    renderPage();
    const table = await screen.findByTestId("tokens-table");
    expect(table.tagName).toBe("TABLE");
    const caption = table.querySelector("caption");
    expect(caption).toHaveClass("sr-only");
    expect(caption).toHaveTextContent("API tokens");
    const headers = within(table).getAllByRole("columnheader");
    expect(headers.map((h) => h.textContent)).toEqual(["Token", "Created", "Actions"]);
    for (const header of headers) expect(header).toHaveAttribute("scope", "col");
    expect(rows()).toHaveLength(2);
  });

  it("shows a loading skeleton with an announced status until the list arrives", async () => {
    let release: (value: unknown) => void = () => undefined;
    handler = (config) => new Promise((resolve) => (release = () => resolve(ok(config, tokens))));
    renderPage();
    expect(screen.getByTestId("tokens-skeleton")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading API tokens");
    await waitFor(() => expect(calls).toHaveLength(1));
    await act(async () => release(null));
    expect(await screen.findByTestId("tokens-table")).toBeInTheDocument();
    expect(screen.queryByTestId("tokens-skeleton")).toBeNull();
  });

  it("shows the created date in a time element with a machine readable value, in the current language", async () => {
    renderPage();
    const first = (await screen.findAllByTestId("token-row"))[0]!;
    const time = first.querySelector("time");
    expect(time).not.toBeNull();
    expect(time!.getAttribute("datetime")).toBe(new Date(NOW - 86_400_000).toISOString());
    expect(time!.textContent).toBe(new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(new Date(NOW - 86_400_000)));
  });
});

describe("masking and accessible names (UI checker flags 3 and 6)", () => {
  it("masks every token by default with the shared rule and keeps the full value out of the DOM", async () => {
    renderPage();
    await screen.findByTestId("tokens-table");
    const values = screen.getAllByTestId("token-value");
    expect(values.map((v) => v.textContent)).toEqual([maskToken(T1), maskToken(T2)]);
    expect(values[0]!.textContent).toBe("ragflow-••••••••aaa1");
    for (const secret of [T1, T2, "middle-secret"]) {
      expect(document.body.innerHTML).not.toContain(secret);
      expect(document.body.textContent).not.toContain(secret);
    }
  });

  it("names every icon button with the token tail only, never the full token", async () => {
    renderPage();
    await screen.findByTestId("tokens-table");
    const first = rowFor("aaa1");
    for (const name of ["Show token ending aaa1", "Copy token ending aaa1", "Delete token ending aaa1"]) {
      expect(within(first).getByRole("button", { name })).toBeInTheDocument();
    }
    for (const button of within(screen.getByTestId("tokens-table")).getAllByRole("button")) {
      expect(button.getAttribute("aria-label") ?? "").not.toContain("middle-secret");
      expect(button.textContent ?? "").not.toContain("ragflow");
    }
  });

  it("reveals only the clicked row, toggles aria-pressed and the accessible name, and hides again", async () => {
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    const toggle = within(rowFor("aaa1")).getByTestId("token-reveal");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await user.click(toggle);
    expect(within(rowFor("aaa1")).getByTestId("token-value")).toHaveTextContent(T1);
    expect(within(rowFor("aaa1")).getByTestId("token-value")).toHaveClass("break-all");
    expect(within(rowFor("bbb2")).getByTestId("token-value").textContent).toBe(maskToken(T2));
    const pressed = within(rowFor("aaa1")).getByRole("button", { name: "Hide token ending aaa1" });
    expect(pressed).toHaveAttribute("aria-pressed", "true");
    await user.click(pressed);
    expect(within(rowFor("aaa1")).getByTestId("token-value").textContent).toBe(maskToken(T1));
    expect(document.body.innerHTML).not.toContain(T1);
  });

  it("forgets what was revealed when the page is left", async () => {
    const user = newUser();
    const view = renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("aaa1")).getByTestId("token-reveal"));
    expect(document.body.textContent).toContain(T1);
    view.unmount();
    expect(document.body.textContent).not.toContain(T1);
    renderPage();
    await screen.findByTestId("tokens-table");
    expect(screen.getAllByTestId("token-value")[0]!.textContent).toBe(maskToken(T1));
  });

  it("renders values as text only: a hostile value is never interpreted as markup", async () => {
    const hostile = "ragflow-<img src=x onerror=alert(1)>-0000000000-zzz9";
    tokens = [row(hostile)];
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(screen.getByTestId("token-reveal"));
    expect(screen.getByTestId("token-value")).toHaveTextContent(hostile);
    expect(document.body.querySelector("img")).toBeNull();
  });
});

describe("copy", () => {
  it("writes the full token while it is masked, toasts, and swaps the icon for two seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubClipboard(async (text) => void writeText(text));
    renderPage();
    await screen.findByTestId("tokens-table");
    const copy = within(rowFor("aaa1")).getByTestId("token-copy");
    await user.click(copy);
    expect(writeText).toHaveBeenCalledExactlyOnceWith(T1);
    expect(await screen.findByText("Token copied")).toBeInTheDocument();
    expect(copy).toHaveAttribute("data-copied", "true");
    expect(within(rowFor("aaa1")).getByTestId("token-value").textContent).toBe(maskToken(T1));
    act(() => void vi.advanceTimersByTime(2000));
    expect(copy).toHaveAttribute("data-copied", "false");
  });

  it("arms no confirmation timer when the row is gone before the clipboard write settles (IN-F11)", async () => {
    let settle: () => void = () => undefined;
    const pending = new Promise<void>((resolve) => {
      settle = resolve;
    });
    const user = userEvent.setup();
    stubClipboard(() => pending);
    const view = renderPage();
    await screen.findByTestId("tokens-table");
    const timers = vi.spyOn(globalThis, "setTimeout");
    await user.click(within(rowFor("aaa1")).getByTestId("token-copy"));
    view.unmount();
    timers.mockClear();
    await act(async () => {
      settle();
      await pending;
    });
    expect(timers.mock.calls.filter(([, delay]) => delay === 2000)).toEqual([]);
    timers.mockRestore();
  });

  it("does not put the token in the toast", async () => {
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("bbb2")).getByTestId("token-copy"));
    const toast = await screen.findByText("Token copied");
    expect(toast.closest("[data-sonner-toast]")?.textContent).not.toContain("middle-secret");
  });

  it("handles a rejected clipboard write: reveals the token and says it could not copy, with no success toast", async () => {
    const user = userEvent.setup();
    stubClipboard(() => Promise.reject(new DOMException("denied", "NotAllowedError")));
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("aaa1")).getByTestId("token-copy"));
    expect(await screen.findByText("Couldn't copy")).toBeInTheDocument();
    expect(screen.getByText("Select the token and copy it manually.")).toBeInTheDocument();
    expect(screen.queryByText("Token copied")).toBeNull();
    expect(within(rowFor("aaa1")).getByTestId("token-value")).toHaveTextContent(T1);
  });

  it("handles a missing clipboard API the same way, without a fallback that needs a hidden input", async () => {
    const user = userEvent.setup();
    stubClipboard("absent");
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("aaa1")).getByTestId("token-copy"));
    expect(await screen.findByText("Couldn't copy")).toBeInTheDocument();
    expect(within(rowFor("aaa1")).getByTestId("token-value")).toHaveTextContent(T1);
    expect(document.querySelectorAll("textarea")).toHaveLength(0);
  });
});

describe("empty, error and forbidden states", () => {
  it("shows the empty state heading as h2 with a single primary Create token and no header action", async () => {
    tokens = [];
    renderPage();
    const heading = await screen.findByRole("heading", { level: 2, name: "No API tokens yet" });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText("Create a token to call the devRag API from your own code.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create token" })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("API tokens");
    expect(screen.queryByTestId("tokens-table")).toBeNull();
  });

  it("shows an in-place error with the noun and retries the list", async () => {
    handler = (config) => failure(config, 500, 500, "boom internals");
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByRole("heading", { name: "Couldn't load API tokens" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("boom internals");
    expect(screen.queryByRole("button", { name: "Create token" })).toBeNull();
    handler = defaultHandler;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("tokens-table")).toBeInTheDocument();
  });

  it("shows a non-owner member a clear owner-only state and no token data", async () => {
    handler = (config) => failure(config, 403, 403, "forbidden");
    renderPage();
    const state = await screen.findByTestId("tokens-forbidden");
    expect(state).toHaveTextContent("Only the workspace owner can manage API tokens");
    expect(screen.queryByTestId("tokens-table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Create token" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});

describe("create flow", () => {
  it("creates immediately, opens the dialog with the full token and a Copy token action, and never says it is shown once", async () => {
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(screen.getByTestId("token-create"));
    const dialog = await screen.findByTestId("token-created-dialog");
    expect(callsTo("post")).toHaveLength(1);
    expect(within(dialog).getByRole("heading", { name: "API token created" })).toBeInTheDocument();
    expect(within(dialog).getByLabelText("API token")).toHaveValue(T3);
    expect(within(dialog).getByLabelText("API token")).toHaveAttribute("readonly");
    const text = dialog.textContent ?? "";
    expect(text).toContain("You can view it again from this page.");
    expect(text).not.toMatch(/can.?t be viewed again|only once|shown once|won.?t be shown again/i);
    await user.click(within(dialog).getByRole("button", { name: "Copy token" }));
    expect(writeText).toHaveBeenCalledExactlyOnceWith(T3);
    expect(await screen.findByText("Token copied")).toBeInTheDocument();
  });

  it("closes with Done, returns focus to the Create button, lists the new token first and masked, and drops the value from the DOM", async () => {
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    const create = screen.getByTestId("token-create");
    await user.click(create);
    const dialog = await screen.findByTestId("token-created-dialog");
    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByTestId("token-created-dialog")).toBeNull());
    await waitFor(() => expect(screen.getByTestId("token-create")).toHaveFocus());
    await waitFor(() => expect(screen.getAllByTestId("token-row")).toHaveLength(3));
    expect(screen.getAllByTestId("token-value")[0]!.textContent).toBe(maskToken(T3));
    expect(document.body.innerHTML).not.toContain(T3);
  });

  it("also closes with Escape", async () => {
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(screen.getByTestId("token-create"));
    await screen.findByTestId("token-created-dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("token-created-dialog")).toBeNull());
  });

  it("creates the first token from the empty state", async () => {
    tokens = [];
    const user = newUser();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Create token" }));
    expect(await screen.findByTestId("token-created-dialog")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByTestId("tokens-table")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("token-create")).toHaveFocus());
  });

  it("sends exactly one request while a create is pending", async () => {
    let release: (value: unknown) => void = () => undefined;
    handler = (config) =>
      String(config.method).toLowerCase() === "post"
        ? new Promise((resolve) => (release = () => resolve(defaultHandler(config))))
        : defaultHandler(config);
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    const create = screen.getByTestId("token-create");
    await user.click(create);
    await waitFor(() => expect(callsTo("post")).toHaveLength(1));
    expect(create).toHaveAttribute("aria-disabled", "true");
    await user.click(create);
    await user.keyboard("{Enter}");
    expect(callsTo("post")).toHaveLength(1);
    await act(async () => release(null));
    expect(await screen.findByTestId("token-created-dialog")).toBeInTheDocument();
    expect(callsTo("post")).toHaveLength(1);
  });

  it.each([
    ["the cap (409)", 409, 409, "api token limit reached", {}, "Token limit reached"],
    ["the rate limit (429)", 429, 400, "too many requests", { "Retry-After": "120" }, "Too many tokens created"],
    ["a non-owner (403)", 403, 403, "forbidden", {}, "Couldn't create token"],
    ["a server error", 500, 500, "stack trace internals", {}, "Couldn't create token"],
  ])("answers %s with its own clear message and does not open the dialog", async (_name, status, code, message, headers, title) => {
    handler = (config) =>
      String(config.method).toLowerCase() === "post" ? failure(config, status, code, message, headers) : defaultHandler(config);
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(screen.getByTestId("token-create"));
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByTestId("token-created-dialog")).toBeNull();
    expect(document.body.textContent).not.toContain("stack trace internals");
    expect(document.body.textContent).not.toContain("middle-secret-2222");
    expect(screen.getByTestId("token-create")).not.toHaveAttribute("aria-disabled", "true");
  });
});

describe("delete flow", () => {
  it("opens an alert dialog naming the tail, focuses Keep token first, and does not close on an overlay click", async () => {
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("aaa1")).getByTestId("token-delete"));
    const dialog = await screen.findByTestId("token-delete-dialog");
    expect(dialog).toHaveAttribute("role", "alertdialog");
    expect(within(dialog).getByRole("heading", { name: "Delete API token?" })).toBeInTheDocument();
    expect(dialog).toHaveTextContent("The token ending aaa1 stops working immediately");
    expect(dialog.textContent).not.toContain("middle-secret");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Keep token" })).toHaveFocus());
    expect(within(dialog).getByRole("button", { name: "Delete token" })).toBeInTheDocument();
    const overlay = document.querySelector<HTMLElement>(".fixed.inset-0");
    expect(overlay).not.toBeNull();
    await user.click(overlay!);
    expect(screen.getByTestId("token-delete-dialog")).toBeInTheDocument();
    expect(callsTo("delete")).toHaveLength(0);
  });

  it("keeps the token and returns focus to the row's Delete button", async () => {
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    const trigger = within(rowFor("bbb2")).getByTestId("token-delete");
    await user.click(trigger);
    await user.click(await screen.findByRole("button", { name: "Keep token" }));
    await waitFor(() => expect(screen.queryByTestId("token-delete-dialog")).toBeNull());
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(callsTo("delete")).toHaveLength(0);
    expect(rows()).toHaveLength(2);
  });

  it("confirms with the row's own token, removes the row, toasts, and moves focus to the table caption", async () => {
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("bbb2")).getByTestId("token-delete"));
    await user.click(await screen.findByRole("button", { name: "Delete token" }));
    expect(await screen.findByText("Token deleted")).toBeInTheDocument();
    const sent = callsTo("delete");
    expect(sent).toHaveLength(1);
    expect(sent[0]!.url).toBe(`/api/v1/system/tokens/${encodeURIComponent(T2)}`);
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(within(rows()[0]!).getByTestId("token-value").textContent).toBe(maskToken(T1));
    await waitFor(() => expect(screen.getByTestId("tokens-table").querySelector("caption")).toHaveFocus());
    expect(document.body.textContent).not.toContain("middle-secret");
  });

  it("sends the id of the row that was clicked, not of another row", async () => {
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("aaa1")).getByTestId("token-delete"));
    await user.click(await screen.findByRole("button", { name: "Delete token" }));
    await waitFor(() => expect(callsTo("delete")).toHaveLength(1));
    expect(decodeURIComponent(callsTo("delete")[0]!.url!.split("/").pop()!)).toBe(T1);
  });

  it("refreshes the list on a 404 instead of showing internals", async () => {
    handler = (config) => {
      if (String(config.method).toLowerCase() === "delete") {
        tokens = tokens.filter((t) => t.token !== T2);
        return failure(config, 404, 404, "token not found");
      }
      return defaultHandler(config);
    };
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("bbb2")).getByTestId("token-delete"));
    await user.click(await screen.findByRole("button", { name: "Delete token" }));
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(screen.queryByTestId("token-delete-dialog")).toBeNull();
    expect(screen.queryByText(/not found/i)).toBeNull();
    expect(screen.queryByText("Token deleted")).toBeNull();
  });

  it("shows a fixed error toast and keeps the list on a failed delete", async () => {
    handler = (config) => (String(config.method).toLowerCase() === "delete" ? failure(config, 500, 500, "sql internals") : defaultHandler(config));
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("aaa1")).getByTestId("token-delete"));
    await user.click(await screen.findByRole("button", { name: "Delete token" }));
    expect(await screen.findByText("Couldn't delete token")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("sql internals");
    await waitFor(() => expect(screen.queryByTestId("token-delete-dialog")).toBeNull());
    expect(rows()).toHaveLength(2);
  });
});

describe("token values stay out of storage, console and the query cache after sign out (T-02-98, T-02-99)", () => {
  it("never writes a token to local or session storage, the URL, the title or the console", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((level) => vi.spyOn(console, level).mockImplementation(() => undefined));
    const user = newUser();
    renderPage();
    await screen.findByTestId("tokens-table");
    await user.click(within(rowFor("aaa1")).getByTestId("token-reveal"));
    await user.click(within(rowFor("aaa1")).getByTestId("token-copy"));
    await user.click(screen.getByTestId("token-create"));
    await screen.findByTestId("token-created-dialog");
    const dump = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage });
    for (const secret of ["middle-secret", T1, T3]) expect(dump).not.toContain(secret);
    expect(window.location.href).not.toContain("ragflow-");
    expect(document.title).not.toContain("ragflow-");
    for (const spy of spies) expect(JSON.stringify(spy.mock.calls)).not.toContain("middle-secret");
    for (const spy of spies) spy.mockRestore();
  });

  it("is cleared by purgeSession, so a signed-out browser keeps no token in the query cache", async () => {
    renderPage();
    await screen.findByTestId("tokens-table");
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => q.state.data))).toContain("middle-secret");
    act(() => purgeSession({ toast: false, navigate: false }));
    expect(client.getQueryCache().getAll()).toHaveLength(0);
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
});
