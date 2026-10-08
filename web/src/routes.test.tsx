import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError, AxiosHeaders, type AxiosAdapter } from "axios";
import { createMemoryRouter, RouterProvider } from "react-router";
import { Activity, House } from "lucide-react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { routes, type RouteEntry } from "@/constants/routes";
import { ShellError } from "@/pages/route-error";
import { buildRoutes } from "@/routes";
import { http } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { waitUntil } from "@/test/wait-until";
import { setAuthorization } from "@/utils/authorization";

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
let infoGate: Promise<void> = Promise.resolve();
/** Session recovery answers with a real user; every other request is refused like a downed engine. */
const refuse: AxiosAdapter = async (config) => {
  if (config.url === "/v1/user/info") {
    await infoGate;
    return { data: { code: 0, message: "", data: userDto }, status: 200, statusText: "200", headers: new AxiosHeaders(), config } as never;
  }
  throw new AxiosError("Network Error", "ERR_NETWORK", config);
};

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
beforeEach(() => {
  infoGate = Promise.resolve();
  useUserStore.getState().reset();
  http.defaults.adapter = refuse;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
});

function renderAt(path: string, entries?: readonly RouteEntry[]) {
  const router = createMemoryRouter(buildRoutes(entries), { initialEntries: [path] });
  const view = render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return Object.assign(view, { router });
}

function signIn() {
  setAuthorization("tok-a");
}

describe("auth guard in the route table (UI-02, UI-07)", () => {
  it("redirects a signed-out visitor at /system-status to /login?next=%2Fsystem-status inside the bare layout, never showing the shell", async () => {
    const { router } = renderAt("/system-status");
    expect(await screen.findByTestId("layout-bare")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("?next=%2Fsystem-status");
    expect(screen.queryByTestId("layout-standard")).toBeNull();
    expect(screen.queryByRole("heading", { name: "System status" })).toBeNull();
  });

  it("keeps /login public and renders the sign-in page in the bare layout without a token", async () => {
    const { router } = renderAt("/login");
    expect(await screen.findByTestId("login-page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(screen.getByTestId("layout-bare")).toBeInTheDocument();
    expect(screen.getByTestId("language-switch")).toBeInTheDocument();
    expect(screen.queryByTestId("layout-standard")).toBeNull();
  });

  it("keeps /forgot-password public: the reset page renders in the bare layout without a token and is not sent to /login", async () => {
    const { router } = renderAt("/forgot-password");
    expect(await screen.findByTestId("forgot-page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/forgot-password");
    expect(screen.getByTestId("layout-bare")).toBeInTheDocument();
    expect(screen.getByTestId("language-switch")).toBeInTheDocument();
    expect(screen.queryByTestId("layout-standard")).toBeNull();
  });

  it("keeps unknown paths public: Not Found renders without a token", async () => {
    const { router } = renderAt("/nope");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/nope");
    expect(screen.getByTestId("layout-bare")).toBeInTheDocument();
    expect(screen.queryByTestId("layout-standard")).toBeNull();
  });

  it("renders Not Found inside the standard layout once signed in", async () => {
    signIn();
    renderAt("/nope");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByTestId("layout-standard")).toBeInTheDocument();
  });

  it("never flashes the shell or the page before session recovery resolves", async () => {
    signIn();
    let release: () => void = () => undefined;
    infoGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderAt("/system-status");
    await waitUntil(() => screen.queryByTestId("session-skeleton") !== null, { describe: "session skeleton" });
    expect(screen.getByTestId("layout-bare")).toBeInTheDocument();
    expect(screen.queryByTestId("layout-standard")).toBeNull();
    expect(screen.queryByRole("heading", { name: "System status" })).toBeNull();
    release();
    expect(await screen.findByTestId("layout-standard")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "System status" })).toBeInTheDocument();
    expect(useUserStore.getState().user?.nickname).toBe("Ada");
  });
});

describe("the root entry redirect (UI-02)", () => {
  it("sends a signed-out visitor at / to /login with no next parameter and never shows the shell", async () => {
    const { router } = renderAt("/");
    expect(await screen.findByTestId("layout-bare")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("");
    expect(screen.queryByTestId("layout-standard")).toBeNull();
  });

  it("sends a signed-in visitor at / to /home and renders the dashboard", async () => {
    signIn();
    const { router } = renderAt("/");
    expect(await screen.findByRole("heading", { name: "Welcome, Ada" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/home");
    expect(screen.getByTestId("layout-standard")).toBeInTheDocument();
    expect(screen.getByTestId("stat-role")).toHaveTextContent("Owner");
  });

  it("redirects a signed-out visitor at /home to /login?next=%2Fhome, never showing the shell", async () => {
    const { router } = renderAt("/home");
    expect(await screen.findByTestId("layout-bare")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("?next=%2Fhome");
    expect(screen.queryByTestId("layout-standard")).toBeNull();
  });

  it("keeps the root redirect public and the status page guarded in the registry", () => {
    const root = routes.find((r) => r.path === "/");
    expect(root?.auth).toBe("none");
    expect(root?.nav).toBeUndefined();
    expect(root?.redirect?.({ signedIn: true })).toBe("/home");
    expect(root?.redirect?.({ signedIn: false })).toBe("/login");
    const home = routes.find((r) => r.path === "/home");
    expect(home?.auth).toBe("required");
    expect(home?.layout).toBe("standard");
    expect(home?.nav).toMatchObject({ labelKey: "nav.home", order: 1, group: "platform" });
    expect(home?.nav?.icon).toBe(House);
    const status = routes.find((r) => r.path === "/system-status");
    expect(status?.auth).toBe("required");
    expect(status?.layout).toBe("standard");
    expect(status?.nav).toMatchObject({ labelKey: "nav.systemStatus", order: 2, group: "platform" });
    expect(status?.nav?.icon).toBe(Activity);
  });
});

describe("blocked browser storage (WR-F01)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function blockStorage(): void {
    const denied = () => {
      throw new DOMException("The operation is insecure.", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(denied);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(denied);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(denied);
  }

  it("renders the sign-in page and the root redirect instead of the error boundary", async () => {
    blockStorage();
    const root = renderAt("/");
    expect(await screen.findByTestId("login-page")).toBeInTheDocument();
    expect(root.router.state.location.pathname).toBe("/login");
    expect(screen.queryByRole("heading", { name: "Something went wrong" })).toBeNull();
  });

  it("lets a visitor sign in for the lifetime of the tab: the token lives in memory and recovery succeeds", async () => {
    blockStorage();
    setAuthorization("tok-memory");
    renderAt("/home");
    expect(await screen.findByRole("heading", { name: "Welcome, Ada" })).toBeInTheDocument();
    expect(screen.getByTestId("layout-standard")).toBeInTheDocument();
  });
});

describe("route table", () => {
  it("renders every registry route inside its declared layout", async () => {
    signIn();
    expect(routes.length).toBeGreaterThan(0);
    const home = renderAt("/home");
    expect(await screen.findByTestId("layout-standard")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Welcome, Ada" })).toBeInTheDocument();
    home.unmount();
    const status = renderAt("/system-status");
    expect(await screen.findByTestId("layout-standard")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "System status" })).toBeInTheDocument();
    status.unmount();
    renderAt("/anything");
    expect(await screen.findByTestId("layout-standard")).toBeInTheDocument();
  });

  it.each(["/datasets"])("renders the honest Not Found page for unbuilt %s", async (path) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByText("404")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to home" })).toHaveAttribute("href", "/home");
    expect(screen.queryByText(/coming soon/i)).toBeNull();
  });

  it("renders a test-only fullBleed route inside layout-fullbleed", async () => {
    const entries: RouteEntry[] = [
      ...routes,
      { path: "/canvas-test", layout: "fullBleed", auth: "none", component: () => import("@/pages/not-found") },
    ];
    renderAt("/canvas-test", entries);
    expect(await screen.findByTestId("layout-fullbleed")).toBeInTheDocument();
    expect(screen.queryByTestId("layout-standard")).toBeNull();
  });

  it("renders a test-only bare route inside layout-bare", async () => {
    const entries: RouteEntry[] = [
      ...routes,
      { path: "/bare-test", layout: "bare", auth: "none", component: () => import("@/pages/not-found") },
    ];
    renderAt("/bare-test", entries);
    expect(await screen.findByTestId("layout-bare")).toBeInTheDocument();
  });

  it("shows the delayed route skeleton while a lazy chunk is pending", async () => {
    signIn();
    const entries: RouteEntry[] = [
      ...routes,
      { path: "/slow", layout: "standard", auth: "none", component: () => new Promise(() => undefined) },
    ];
    renderAt("/slow", entries);
    expect(screen.queryByTestId("route-skeleton")).toBeNull();
    await waitUntil(() => screen.queryByTestId("route-skeleton") !== null, { describe: "route skeleton" });
  });

  it("renders the route error state inside the layout when a lazy chunk fails to load", async () => {
    signIn();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const entries: RouteEntry[] = [
      ...routes,
      { path: "/broken", layout: "standard", auth: "none", component: () => Promise.reject(new Error("chunk failed")) },
    ];
    renderAt("/broken", entries);
    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload page" })).toBeInTheDocument();
    expect(screen.getByTestId("layout-standard")).toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it("falls back to the bare layout when the shell itself throws", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const router = createMemoryRouter(
      [
        {
          element: <Boom />,
          errorElement: <ShellError />,
          children: [{ path: "*", element: <p>never</p> }],
        },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);
    expect(await screen.findByTestId("layout-bare")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    vi.restoreAllMocks();
  });
});

function Boom(): JSX.Element {
  throw new Error("shell failed");
}
