import { Activity, House, type LucideIcon } from "lucide-react";
import type { ComponentType } from "react";
import { HOME_PATH } from "@/utils/safe-next";

/**
 * The single typed route registry (UI-01, D-19, 01-UI-SPEC.md).
 *
 * Planned groups, listed as text only and never rendered: Datasets, Chat, Agents, Settings, Admin.
 * Later phases add their entries here; nothing else in the shell changes. Routes that are not built are
 * absent, so the sidebar shows only real pages and unknown paths reach the Not Found page.
 */
export type LayoutKind = "standard" | "fullBleed" | "bare";

export type NavGroup = "platform" | "account";

/** Order in which captioned groups render in the sidebar. */
export const NAV_GROUPS: readonly NavGroup[] = ["platform", "account"];

export interface RouteNav {
  /** i18n key, resolved at render so the label follows the language. */
  labelKey: string;
  icon: LucideIcon;
  order: number;
  /** Captioned sidebar group (UI-SPEC "Navigation entries"). */
  group: NavGroup;
}

export interface RouteEntry {
  path: string;
  layout: LayoutKind;
  /** `required` entries sit behind RequireAuth (UI-02); `none` entries stay public. */
  auth: "none" | "required";
  /** Lazy page. Absent on redirect entries. */
  component?: () => Promise<{ default: ComponentType }>;
  /**
   * Redirect entry: renders no page and replaces the location with the returned same-origin path.
   * The target is computed from the stored token, never from a flag in client state.
   */
  redirect?: (session: { signedIn: boolean }) => string;
  nav?: RouteNav;
}

/** Where `/` sends a signed-in visitor: the home dashboard (UI-09). Shared with the post sign-in default in utils/safe-next. */
export const ROOT_SIGNED_IN_TARGET = HOME_PATH;

export const routes: readonly RouteEntry[] = [
  {
    path: "/",
    layout: "bare",
    auth: "none",
    redirect: ({ signedIn }) => (signedIn ? ROOT_SIGNED_IN_TARGET : "/login"),
  },
  {
    path: "/login",
    layout: "bare",
    auth: "none",
    component: () => import("@/pages/login"),
  },
  {
    path: "/home",
    layout: "standard",
    auth: "required",
    component: () => import("@/pages/home"),
    nav: { labelKey: "nav.home", icon: House, order: 1, group: "platform" },
  },
  {
    path: "/system-status",
    layout: "standard",
    auth: "required",
    component: () => import("@/pages/system-status"),
    nav: { labelKey: "nav.systemStatus", icon: Activity, order: 2, group: "platform" },
  },
  {
    path: "*",
    layout: "standard",
    auth: "none",
    component: () => import("@/pages/not-found"),
  },
];

/** Entries that appear in navigation: only those with `nav`, ordered. */
export function navEntries(entries: readonly RouteEntry[] = routes): RouteEntry[] {
  return entries.filter((e) => e.nav !== undefined && e.path !== "*").sort((a, b) => (a.nav?.order ?? 0) - (b.nav?.order ?? 0));
}

export function pathSlug(path: string): string {
  const slug = path.replace(/^\/+|\/+$/g, "").replace(/\//g, "-");
  return slug === "" ? "root" : slug;
}
