import { lazy, Suspense, type ComponentType } from "react";
import { RouteSkeleton } from "@/components/route-skeleton";

/** Wraps a dynamic import in React.lazy plus a Suspense boundary with the delayed route skeleton. */
export function withLazyRoute(importer: () => Promise<{ default: ComponentType }>) {
  const Lazy = lazy(importer);
  return (
    <Suspense fallback={<RouteSkeleton />}>
      <Lazy />
    </Suspense>
  );
}
