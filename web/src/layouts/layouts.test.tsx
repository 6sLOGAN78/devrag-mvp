import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentType } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { Activity } from "lucide-react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { AppSidebar } from "@/components/app-sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { RouteSkeleton } from "@/components/route-skeleton";
import i18n from "@/i18n";
import { navEntries, routes, type RouteEntry } from "@/constants/routes";
import { waitUntil } from "@/test/wait-until";
import { useUserStore } from "@/stores/user-store";
import { THEME_KEY } from "@/utils/theme";
import { BareLayout } from "./bare-layout";
import { FullBleedLayout } from "./full-bleed-layout";
import { StandardLayout } from "./standard-layout";

beforeAll(() => {
  vi.stubGlobal(
    "matchMedia",
    (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  );
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

function renderIn(Layout: ComponentType, path = "/") {
  const router = createMemoryRouter([{ element: <Layout />, children: [{ path: "*", element: <p>page body</p> }] }], {
    initialEntries: [path],
  });
  return render(<RouterProvider router={router} />);
}

describe("StandardLayout", () => {
  it("renders landmarks, test id and wordmark", () => {
    renderIn(StandardLayout);
    expect(screen.getByTestId("layout-standard")).toBeInTheDocument();
    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent(i18n.t("app.wordmark"));
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "main");
    expect(within(main).getByText("page body")).toBeInTheDocument();
  });

  it("makes the skip link the first focusable element", async () => {
    renderIn(StandardLayout);
    await userEvent.tab();
    const skip = screen.getByText("Skip to main content");
    expect(skip).toHaveFocus();
    expect(skip).toHaveAttribute("href", "#main");
  });

  it("lists exactly one nav item, System status, marked current on /system-status", () => {
    renderIn(StandardLayout, "/system-status");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    const links = within(nav).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent("System status");
    expect(links[0]).toHaveAttribute("aria-current", "page");
    expect(screen.getByTestId("nav-item-system-status")).toBe(links[0]);
    expect(within(links[0]).getByTestId("nav-active-indicator")).toHaveClass("w-0.5");
    expect(links[0].querySelector("svg")).toHaveClass("text-primary");
  });

  it("does not mark the item current or accent its icon on another path", () => {
    renderIn(StandardLayout, "/datasets");
    const link = screen.getByTestId("nav-item-system-status");
    expect(link).not.toHaveAttribute("aria-current");
    expect(link.querySelector("svg")).not.toHaveClass("text-primary");
    expect(screen.queryByTestId("nav-active-indicator")).toBeNull();
  });

  it("never renders unbuilt or placeholder navigation entries", () => {
    renderIn(StandardLayout);
    for (const label of ["Datasets", "Chat", "Agents", "Settings", "Admin", "Login"]) {
      expect(screen.queryByText(label)).toBeNull();
    }
    expect(screen.queryByText(/coming soon/i)).toBeNull();
  });

  it("holds no user menu in the header while no user is signed in", () => {
    renderIn(StandardLayout);
    const header = screen.getByRole("banner");
    expect(within(header).queryByTestId("user-menu")).toBeNull();
    expect(within(header).queryByRole("img")).toBeNull();
  });

  it("fills the reserved header slot with the account menu after the theme toggle once a user is signed in", () => {
    useUserStore.getState().setUser({
      id: "u1", nickname: "Ada Lovelace", email: "ada@example.test", avatar: "", language: "", colorSchema: "", tenantId: "t1", tenantName: "", role: "owner", isSuperuser: false,
    });
    renderIn(StandardLayout);
    const header = screen.getByRole("banner");
    const theme = within(header).getByTestId("theme-toggle");
    const menu = within(header).getByRole("button", { name: "Account menu" });
    expect(theme.compareDocumentPosition(menu) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    useUserStore.getState().reset();
  });

  it("offers Light, Dark and System and persists the choice", async () => {
    renderIn(StandardLayout);
    const toggle = screen.getByTestId("theme-toggle");
    expect(toggle).toHaveAttribute("aria-label", "Change theme");
    await userEvent.click(toggle);
    expect(await screen.findByRole("menuitem", { name: "Light" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "System" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Dark" }));
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");
    await userEvent.click(screen.getByTestId("theme-toggle"));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Light" }));
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
    expect(document.documentElement).not.toHaveClass("dark");
    await userEvent.click(screen.getByTestId("theme-toggle"));
    await userEvent.click(await screen.findByRole("menuitem", { name: "System" }));
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("opens the mobile sheet, traps focus inside and closes on Escape", async () => {
    renderIn(StandardLayout);
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: i18n.t("nav.openMenu") }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("link", { name: "System status" })).toBeInTheDocument();
    for (let i = 0; i < 6; i += 1) {
      await userEvent.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    await userEvent.keyboard("{Escape}");
    await waitUntil(() => screen.queryByRole("dialog") === null);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("FullBleedLayout and BareLayout", () => {
  it("renders the full-bleed layout with a header and an unpadded main", () => {
    renderIn(FullBleedLayout);
    expect(screen.getByTestId("layout-fullbleed")).toBeInTheDocument();
    expect(screen.getByRole("banner")).toBeInTheDocument();
    const main = screen.getByRole("main");
    expect(main.className).toContain("h-[calc(100dvh-56px)]");
    expect(main.className).not.toMatch(/\bp-\d/);
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("renders the bare layout without chrome", () => {
    renderIn(BareLayout);
    expect(screen.getByTestId("layout-bare")).toBeInTheDocument();
    expect(screen.queryByRole("banner")).toBeNull();
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.getByText("page body")).toBeInTheDocument();
  });
});

describe("registry", () => {
  it("contains exactly the entries /, /system-status and *", () => {
    expect(routes.map((r) => r.path)).toEqual(["/", "/system-status", "*"]);
    expect(navEntries().map((r) => i18n.t(r.nav?.labelKey ?? ""))).toEqual(["System status"]);
  });

  it("navEntries excludes entries without nav", () => {
    const extra: RouteEntry = { path: "/x", layout: "bare", auth: "none", component: () => Promise.reject(new Error("unused")) };
    expect(navEntries([...routes, extra]).map((r) => r.path)).toEqual(["/system-status"]);
  });
});

describe("AppSidebar nav groups", () => {
  const page = () => Promise.resolve({ default: () => null });
  const entries: RouteEntry[] = [
    { path: "/a", layout: "standard", auth: "required", component: page, nav: { labelKey: "nav.systemStatus", icon: Activity, order: 2, group: "platform" } },
    { path: "/b", layout: "standard", auth: "required", component: page, nav: { labelKey: "nav.systemStatus", icon: Activity, order: 3, group: "account" } },
  ];

  it("renders one captioned, labelled group per value with a rail separator between groups", () => {
    const router = createMemoryRouter([{ path: "*", element: <TooltipProvider><AppSidebar entries={entries} /></TooltipProvider> }]);
    render(<RouterProvider router={router} />);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    const groups = within(nav).getAllByRole("group");
    expect(groups.map((g) => g.getAttribute("aria-labelledby")).every(Boolean)).toBe(true);
    expect(within(nav).getByRole("group", { name: "Platform" })).toBeInTheDocument();
    expect(within(nav).getByRole("group", { name: "Account" })).toBeInTheDocument();
    expect(within(nav).getAllByRole("separator", { hidden: true })).toHaveLength(1);
  });

  it("renders only the groups that have entries, with no separator", () => {
    const router = createMemoryRouter([{ path: "*", element: <TooltipProvider><AppSidebar /></TooltipProvider> }]);
    render(<RouterProvider router={router} />);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getAllByRole("group")).toHaveLength(1);
    expect(within(nav).getByRole("group", { name: "Platform" })).toBeInTheDocument();
    expect(within(nav).queryByRole("separator", { hidden: true })).toBeNull();
  });
});

describe("state components", () => {
  it("EmptyState names the thing, with a generic fallback", () => {
    const { rerender } = render(<EmptyState noun="datasets" body="Datasets hold documents." />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No datasets yet" })).toBeInTheDocument();
    rerender(<EmptyState />);
    expect(screen.getByRole("heading", { name: "Nothing here yet" })).toBeInTheDocument();
  });

  it("EmptyState renders an h1 by default and an h2 inside a page that has its own header", () => {
    const { rerender } = render(<EmptyState noun="datasets" />);
    expect(screen.getByRole("heading", { level: 1, name: "No datasets yet" })).toBeInTheDocument();
    rerender(<EmptyState noun="datasets" as="h2" />);
    expect(screen.getByRole("heading", { level: 2, name: "No datasets yet" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("ErrorState shows heading, body, code and a working Try again action", async () => {
    const onAction = vi.fn();
    render(<ErrorState noun="datasets" code={503} onAction={onAction} />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Couldn't load datasets" })).toBeInTheDocument();
    expect(screen.getByText("Code 503")).toHaveClass("font-mono");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it("RouteSkeleton appears only after the delay", async () => {
    render(<RouteSkeleton />);
    expect(screen.queryByTestId("route-skeleton")).toBeNull();
    await waitUntil(() => screen.queryByTestId("route-skeleton") !== null);
    expect(screen.getByTestId("route-skeleton")).toBeInTheDocument();
  });
});
