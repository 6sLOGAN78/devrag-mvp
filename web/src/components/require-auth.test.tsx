import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RequireAuth } from "@/components/require-auth";
import { Toaster } from "@/components/ui/sonner";
import i18n from "@/i18n";
import { LANG_KEY } from "@/i18n/language";
import { http, registerQueryClient } from "@/services/http";
import { installSessionSync } from "@/services/session-sync";
import { useProfileRequest } from "@/hooks/use-profile-request";
import { setThemeChoice } from "@/utils/theme";
import { useUserStore } from "@/stores/user-store";
import { getAuthorization, setAuthorization } from "@/utils/authorization";
import { waitUntil } from "@/test/wait-until";

const originalAdapter = http.defaults.adapter;

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

type Step = { kind: "ok"; user?: Partial<typeof userDto> } | { kind: "status"; status: number } | { kind: "network" } | { kind: "pending" };
let script: Step[] = [];
let calls: InternalAxiosRequestConfig[] = [];

function respond(config: InternalAxiosRequestConfig, step: Step) {
  const ok = (status: number, data: unknown) =>
    ({ data, status, statusText: String(status), headers: new AxiosHeaders(), config }) as never;
  if (step.kind === "pending") return new Promise<never>(() => undefined);
  if (step.kind === "network") return Promise.reject(new AxiosError("Network Error", "ERR_NETWORK", config));
  if (step.kind === "ok") return Promise.resolve(ok(200, { code: 0, message: "", data: { ...userDto, ...step.user } }));
  const response = ok(step.status, { code: step.status, message: "no", data: null });
  return Promise.reject(new AxiosError(`status ${step.status}`, "ERR_BAD_RESPONSE", config, null, response));
}

const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  return respond(config, script.shift() ?? { kind: "pending" });
};

function Probe({ label }: { label: string }) {
  const location = useLocation();
  return (
    <p data-testid={label}>
      {location.pathname}
      {location.search}
    </p>
  );
}

function renderGuard(path: string, content: JSX.Element = <p>protected content</p>) {
  const router = createMemoryRouter(
    [
      { element: <RequireAuth />, children: [{ path: "/user-setting/profile", element: content }] },
      { path: "/login", element: <Probe label="login-page" /> },
    ],
    { initialEntries: [path] },
  );
  const client = new QueryClient();
  registerQueryClient(client);
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>,
  );
  return { router, client, view };
}

beforeEach(() => {
  script = [];
  calls = [];
  useUserStore.getState().reset();
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  vi.useRealTimers();
});

describe("RequireAuth: signed out", () => {
  it("redirects a guarded route to /login?next= with the encoded path and no toast", async () => {
    renderGuard("/user-setting/profile");
    expect(await screen.findByTestId("login-page")).toHaveTextContent("/login?next=%2Fuser-setting%2Fprofile");
    expect(screen.queryByText("protected content")).toBeNull();
    expect(calls).toHaveLength(0);
    expect(screen.queryByText("Session expired")).toBeNull();
  });

  it("keeps the query string in next", async () => {
    renderGuard("/user-setting/profile?tab=keys&x=1");
    expect(await screen.findByTestId("login-page")).toHaveTextContent("/login?next=%2Fuser-setting%2Fprofile%3Ftab%3Dkeys%26x%3D1");
  });

  it("does not trust a client-side flag: a user in the store without a token still redirects", async () => {
    useUserStore.getState().setUser({
      id: "u1", nickname: "Ada", email: "a@example.test", avatar: "", language: "", colorSchema: "", tenantId: "t1", tenantName: "", role: "owner", isSuperuser: false,
    });
    renderGuard("/user-setting/profile");
    expect(await screen.findByTestId("login-page")).toBeInTheDocument();
    expect(screen.queryByText("protected content")).toBeNull();
  });
});

describe("RequireAuth: session recovery", () => {
  beforeEach(() => setAuthorization("tok-a"));

  it("shows no skeleton before 150 ms and a status skeleton after, never the content", () => {
    vi.useFakeTimers();
    script = [{ kind: "pending" }];
    renderGuard("/user-setting/profile");
    act(() => {
      vi.advanceTimersByTime(149);
    });
    expect(screen.queryByTestId("session-skeleton")).toBeNull();
    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(screen.getByTestId("session-skeleton")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Restoring your session");
    expect(screen.getByTestId("layout-bare")).toBeInTheDocument();
    expect(screen.queryByText("protected content")).toBeNull();
    expect(screen.queryByTestId("login-page")).toBeNull();
  });

  it("fetches GET /v1/user/info with the bearer token before rendering, then stores the user", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    http.defaults.adapter = async (config) => {
      calls.push(config);
      await gate;
      return respond(config, { kind: "ok" });
    };
    renderGuard("/user-setting/profile");
    await waitUntil(() => calls.length === 1, { describe: "info request" });
    expect(calls[0]?.url).toBe("/v1/user/info");
    expect(new AxiosHeaders(calls[0]?.headers as never).get("Authorization")).toBe("Bearer tok-a");
    expect(screen.queryByText("protected content")).toBeNull();
    release();
    expect(await screen.findByText("protected content")).toBeInTheDocument();
    expect(useUserStore.getState().user).toMatchObject({ id: "u1", nickname: "Ada", email: "ada@example.test", tenantId: "t1", role: "owner" });
    expect(getAuthorization()).toBe("tok-a");
  });

  it("applies the user language when there is no explicit local choice", async () => {
    script = [{ kind: "ok", user: { language: "zh" } }];
    renderGuard("/user-setting/profile");
    await screen.findByText("protected content");
    await waitUntil(() => i18n.language === "zh", { describe: "language switched to zh" });
  });

  it("applies a server Dark theme when this browser has no stored choice, and keeps an explicit local one", async () => {
    script = [{ kind: "ok", user: { color_schema: "Dark" } }];
    renderGuard("/user-setting/profile");
    await screen.findByText("protected content");
    await waitUntil(() => document.documentElement.classList.contains("dark"), { describe: "dark class from the server colour schema" });
    expect(localStorage.getItem("devrag.theme")).toBeNull();
    cleanup();
    document.documentElement.classList.remove("dark");
    localStorage.setItem("devrag.theme", "light");
    script = [{ kind: "ok", user: { color_schema: "Dark" } }];
    renderGuard("/user-setting/profile");
    await screen.findByText("protected content");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("keeps an explicit local language choice", async () => {
    localStorage.setItem(LANG_KEY, "en");
    script = [{ kind: "ok", user: { language: "zh" } }];
    renderGuard("/user-setting/profile");
    await screen.findByText("protected content");
    expect(useUserStore.getState().user?.language).toBe("zh");
    expect(i18n.language).toBe("en");
  });

  it("401 purges token, store and cache, toasts once and redirects with next, without a reload", async () => {
    script = [{ kind: "status", status: 401 }];
    const { client } = renderGuard("/user-setting/profile");
    client.setQueryData(["other"], 1);
    expect(await screen.findByTestId("login-page")).toHaveTextContent("/login?next=%2Fuser-setting%2Fprofile");
    expect(getAuthorization()).toBeNull();
    expect(useUserStore.getState().user).toBeNull();
    expect(client.getQueryData(["other"])).toBeUndefined();
    expect(await screen.findAllByText("Session expired")).toHaveLength(1);
    expect(screen.queryByText("protected content")).toBeNull();
  });

  it.each([
    ["a network error", { kind: "network" } as Step],
    ["a 503", { kind: "status", status: 503 } as Step],
    ["a 500", { kind: "status", status: 500 } as Step],
  ])("%s keeps the token and shows an in-place error with Try again and Sign in again", async (_name, step) => {
    script = [step, { kind: "ok" }];
    renderGuard("/user-setting/profile");
    expect(await screen.findByRole("heading", { name: "Couldn't load your session" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in again" })).toBeInTheDocument();
    expect(getAuthorization()).toBe("tok-a");
    expect(screen.queryByTestId("login-page")).toBeNull();
    expect(screen.queryByText("protected content")).toBeNull();
    expect(screen.queryByText("Session expired")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("protected content")).toBeInTheDocument();
    expect(calls).toHaveLength(2);
  });

  it("Sign in again drops the session without the expired toast and goes to /login", async () => {
    script = [{ kind: "status", status: 503 }];
    renderGuard("/user-setting/profile");
    fireEvent.click(await screen.findByRole("button", { name: "Sign in again" }));
    expect(await screen.findByTestId("login-page")).toHaveTextContent("/login?next=%2Fuser-setting%2Fprofile");
    expect(getAuthorization()).toBeNull();
    expect(screen.queryByText("Session expired")).toBeNull();
  });
});

describe("RequireAuth: token changed in another tab (WR-F02)", () => {
  let stopSync: () => void = () => undefined;
  beforeEach(() => {
    setAuthorization("tok-a");
    stopSync = installSessionSync();
  });
  afterEach(() => stopSync());

  /** What the browser does when another tab writes the shared localStorage: the value changes, then the event fires. */
  function otherTabWrites(token: string | null) {
    if (token === null) localStorage.removeItem("Authorization");
    else localStorage.setItem("Authorization", token);
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "Authorization" }));
    });
  }

  it("a replacement token purges user A's identity and cache, then recovers user B with B's token", async () => {
    script = [{ kind: "ok" }, { kind: "ok", user: { id: "u2", nickname: "Bob", email: "bob@example.test" } }];
    const { client } = renderGuard("/user-setting/profile");
    expect(await screen.findByText("protected content")).toBeInTheDocument();
    client.setQueryData(["api-tokens", "t1"], ["secret-token-of-A"]);
    expect(useUserStore.getState().user?.nickname).toBe("Ada");

    otherTabWrites("tok-b");

    expect(client.getQueryData(["api-tokens", "t1"])).toBeUndefined();
    expect(useUserStore.getState().user).toBeNull();
    expect(screen.queryByText("protected content")).toBeNull();
    await waitUntil(() => calls.length === 2, { describe: "second session recovery request" });
    expect(new AxiosHeaders(calls[1]?.headers as never).get("Authorization")).toBe("Bearer tok-b");
    expect(await screen.findByText("protected content")).toBeInTheDocument();
    expect(useUserStore.getState().user).toMatchObject({ id: "u2", nickname: "Bob" });
    expect(client.getQueryData(["api-tokens", "t1"])).toBeUndefined();
    expect(screen.queryByText("Session expired")).toBeNull();
  });

  it("a removed token purges identity and cache and sends the guard to /login without a toast", async () => {
    script = [{ kind: "ok" }];
    const { client } = renderGuard("/user-setting/profile");
    expect(await screen.findByText("protected content")).toBeInTheDocument();
    client.setQueryData(["memberships", "t1"], [{ email: "member@example.test" }]);

    otherTabWrites(null);

    expect(await screen.findByTestId("login-page")).toHaveTextContent("/login?next=%2Fuser-setting%2Fprofile");
    expect(useUserStore.getState().user).toBeNull();
    expect(client.getQueryData(["memberships", "t1"])).toBeUndefined();
    expect(client.getQueryCache().getAll()).toHaveLength(0);
    expect(screen.queryByText("Session expired")).toBeNull();
    expect(calls).toHaveLength(1);
  });

  it("ignores a storage event that carries the same token", async () => {
    script = [{ kind: "ok" }];
    renderGuard("/user-setting/profile");
    expect(await screen.findByText("protected content")).toBeInTheDocument();
    otherTabWrites("tok-a");
    expect(screen.getByText("protected content")).toBeInTheDocument();
    expect(useUserStore.getState().user?.nickname).toBe("Ada");
    expect(calls).toHaveLength(1);
  });
});

describe("RequireAuth: server theme applies at session recovery only (WR-F06, R-120)", () => {
  beforeEach(() => {
    setAuthorization("tok-a");
    document.documentElement.classList.remove("dark");
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.classList.remove("dark");
  });

  function SaveNickname() {
    const save = useProfileRequest();
    return (
      <div>
        <button type="button" onClick={() => setThemeChoice("system")}>
          choose system
        </button>
        <button type="button" onClick={() => save.mutate({ nickname: "Ada L" })}>
          save profile
        </button>
        <p data-testid="saved">{save.isSuccess ? "saved" : "idle"}</p>
      </div>
    );
  }

  it("saving the profile after choosing System does not re-apply the server's Dark theme", async () => {
    script = [{ kind: "ok", user: { color_schema: "Dark" } }, { kind: "ok" }];
    renderGuard("/user-setting/profile", <SaveNickname />);
    await waitUntil(() => document.documentElement.classList.contains("dark"), { describe: "server Dark applied at recovery" });
    fireEvent.click(screen.getByRole("button", { name: "choose system" }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("devrag.theme")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "save profile" }));
    await waitUntil(() => screen.getByTestId("saved").textContent === "saved", { describe: "profile saved" });
    expect(useUserStore.getState().user?.nickname).toBe("Ada L");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("saving the profile does not override an explicit Light choice either", async () => {
    script = [{ kind: "ok", user: { color_schema: "Dark" } }, { kind: "ok" }];
    renderGuard("/user-setting/profile", <SaveNickname />);
    await waitUntil(() => document.documentElement.classList.contains("dark"), { describe: "server Dark applied at recovery" });
    act(() => setThemeChoice("light"));
    fireEvent.click(screen.getByRole("button", { name: "save profile" }));
    await waitUntil(() => screen.getByTestId("saved").textContent === "saved", { describe: "profile saved" });
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
