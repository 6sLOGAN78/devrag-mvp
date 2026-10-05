import type { ComponentType } from "react";
import type { RouteObject } from "react-router";
import RouteError, { ShellError } from "@/pages/route-error";
import { BareLayout } from "@/layouts/bare-layout";
import { FullBleedLayout } from "@/layouts/full-bleed-layout";
import { StandardLayout } from "@/layouts/standard-layout";
import { withLazyRoute } from "@/lib/with-lazy-route";
import { routes as registry, type LayoutKind, type RouteEntry } from "@/constants/routes";

const layouts: Record<LayoutKind, ComponentType> = {
  standard: StandardLayout,
  fullBleed: FullBleedLayout,
  bare: BareLayout,
};

/** Builds the router table from the registry: one layout route per layout kind, children lazy. */
export function buildRoutes(entries: readonly RouteEntry[] = registry): RouteObject[] {
  const kinds = Array.from(new Set(entries.map((e) => e.layout)));
  return kinds.map((kind) => {
    const Layout = layouts[kind];
    return {
      element: <Layout />,
      errorElement: <ShellError />,
      children: entries
        .filter((e) => e.layout === kind)
        .map((e) => ({ path: e.path, element: withLazyRoute(e.component), errorElement: <RouteError /> })),
    };
  });
}
