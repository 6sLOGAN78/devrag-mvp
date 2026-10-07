import type { ComponentType } from "react";
import type { RouteObject } from "react-router";
import { RequireAuth } from "@/components/require-auth";
import { RootRedirect } from "@/components/root-redirect";
import RouteError, { ShellError } from "@/pages/route-error";
import { BareLayout } from "@/layouts/bare-layout";
import { FullBleedLayout } from "@/layouts/full-bleed-layout";
import { PublicStandardLayout } from "@/layouts/public-standard-layout";
import { StandardLayout } from "@/layouts/standard-layout";
import { withLazyRoute } from "@/lib/with-lazy-route";
import { routes as registry, type LayoutKind, type RouteEntry } from "@/constants/routes";

const layouts: Record<LayoutKind, ComponentType> = {
  standard: StandardLayout,
  fullBleed: FullBleedLayout,
  bare: BareLayout,
};

function layoutFor(entry: Pick<RouteEntry, "layout" | "auth">): ComponentType {
  return entry.auth === "none" && entry.layout === "standard" ? PublicStandardLayout : layouts[entry.layout];
}

function elementFor(entry: RouteEntry): JSX.Element {
  if (entry.redirect) return <RootRedirect resolve={entry.redirect} />;
  if (!entry.component) throw new Error(`route ${entry.path} has neither a component nor a redirect`);
  return withLazyRoute(entry.component);
}

/**
 * Builds the router table from the registry: one layout route per layout kind and auth level, children lazy.
 * Entries with `auth: "required"` sit behind RequireAuth, which renders only a skeleton or a redirect until the
 * session is confirmed, so the shell never flashes for a signed-out visitor (UI-02).
 */
export function buildRoutes(entries: readonly RouteEntry[] = registry): RouteObject[] {
  const groups = Array.from(new Set(entries.map((e) => `${e.layout}:${e.auth}`)));
  return groups.map((key) => {
    const members = entries.filter((e) => `${e.layout}:${e.auth}` === key);
    const Layout = layoutFor(members[0]!);
    const layoutRoute: RouteObject = {
      element: <Layout />,
      errorElement: <ShellError />,
      children: members.map((e) => ({ path: e.path, element: elementFor(e), errorElement: <RouteError /> })),
    };
    return members[0]!.auth === "required" ? { element: <RequireAuth />, errorElement: <ShellError />, children: [layoutRoute] } : layoutRoute;
  });
}
