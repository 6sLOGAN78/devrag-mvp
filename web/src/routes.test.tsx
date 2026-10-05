import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError, type AxiosAdapter } from "axios";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { routes, type RouteEntry } from "@/constants/routes";
import { ShellError } from "@/pages/route-error";
import { buildRoutes } from "@/routes";
import { http } from "@/services/http";
import { waitUntil } from "@/test/wait-until";

const originalAdapter = http.defaults.adapter;
const refuse: AxiosAdapter = (config) => Promise.reject(new AxiosError("Network Error", "ERR_NETWORK", config));

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
beforeEach(() => {
  http.defaults.adapter = refuse;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
});

function renderAt(path: string, entries?: readonly RouteEntry[]) {
  const router = createMemoryRouter(buildRoutes(entries), { initialEntries: [path] });
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("route table", () => {
  it("renders every registry route inside its declared layout", async () => {
    expect(routes.length).toBeGreaterThan(0);
    const status = renderAt("/");
    expect(await screen.findByTestId("layout-standard")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "System status" })).toBeInTheDocument();
    status.unmount();
    renderAt("/anything");
    expect(await screen.findByTestId("layout-standard")).toBeInTheDocument();
  });

  it.each(["/login", "/datasets"])("renders the honest Not Found page for unbuilt %s", async (path) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByText("404")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to System status" })).toHaveAttribute("href", "/");
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
    const entries: RouteEntry[] = [
      ...routes,
      { path: "/slow", layout: "standard", auth: "none", component: () => new Promise(() => undefined) },
    ];
    renderAt("/slow", entries);
    expect(screen.queryByTestId("route-skeleton")).toBeNull();
    await waitUntil(() => screen.queryByTestId("route-skeleton") !== null, { describe: "route skeleton" });
  });

  it("renders the route error state inside the layout when a lazy chunk fails to load", async () => {
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
