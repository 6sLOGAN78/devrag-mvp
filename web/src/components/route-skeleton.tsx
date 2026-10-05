import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";

export const ROUTE_SKELETON_DELAY_MS = 150;

/** Route loading placeholder, rendered only after the delay so quick loads never flash. */
export function RouteSkeleton() {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), ROUTE_SKELETON_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, []);
  if (!visible) return null;
  return (
    <div data-testid="route-skeleton" aria-hidden="true" className="flex flex-col gap-6">
      <Skeleton className="h-6 w-[200px]" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    </div>
  );
}
