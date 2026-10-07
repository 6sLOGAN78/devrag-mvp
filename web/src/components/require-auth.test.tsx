import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RequireAuth } from "@/components/require-auth";
import { Toaster } from "@/components/ui/sonner";
import i18n from "@/i18n";
import { LANG_KEY } from "@/i18n/language";
import { http, registerQueryClient } from "@/services/http";
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

function renderGuard(path: string) {
  const router = createMemoryRouter(
    [
      { element: <RequireAuth />, children: [{ path: "/user-setting/profile", element: <p>protected content</p> }] },
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
    expect(i18n.language).toBe("zh");
  });

  it("keeps an explicit local language choice", async () => {
    localStorage.setItem(LANG_KEY, "en");
    script = [{ kind: "ok", user: { language: "zh" } }];
    renderGuard("/user-setting/profile");
    await screen.findByText("protected content");
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
