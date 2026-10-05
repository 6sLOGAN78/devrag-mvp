import { copy } from "@/constants/copy";
import { Activity, type LucideIcon } from "lucide-react";
import type { ComponentType } from "react";

/**
 * The single typed route registry (UI-01, D-19, 01-UI-SPEC.md).
 *
 * Planned groups, listed as text only and never rendered: Datasets, Chat, Agents, Settings, Admin.
 * Later phases add their entries here; nothing else in the shell changes. Routes that are not built are
 * absent, so the sidebar shows only real pages and unknown paths reach the Not Found page.
 */
export type LayoutKind = "standard" | "fullBleed" | "bare";

export interface RouteNav {
  label: string;
  icon: LucideIcon;
  order: number;
}

export interface RouteEntry {
  path: string;
  layout: LayoutKind;
  /** Recorded now, enforced from the auth guard onward (UI-02). */
  auth: "none" | "required";
  component: () => Promise<{ default: ComponentType }>;
  nav?: RouteNav;
}

export const routes: readonly RouteEntry[] = [
  {
    path: "/",
    layout: "standard",
    auth: "none",
    component: () => import("@/pages/system-status"),
    nav: { label: copy.nav.systemStatus, icon: Activity, order: 1 },
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
