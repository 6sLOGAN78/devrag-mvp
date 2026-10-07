import type { ReactNode } from "react";
import { Outlet } from "react-router";

/** No chrome. `children` (even null) replaces the Outlet, so a guard can show a blank shell without ever rendering the route. */
export function BareLayout({ children }: { children?: ReactNode }) {
  return (
    <div data-testid="layout-bare" className="flex min-h-dvh items-center justify-center bg-background p-6 text-foreground">
      <main id="main" tabIndex={-1} className="w-full max-w-md focus:outline-none">
        {children === undefined ? <Outlet /> : children}
      </main>
    </div>
  );
}
