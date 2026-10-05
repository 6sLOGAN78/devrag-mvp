import type { ReactNode } from "react";
import { Outlet } from "react-router";

/** No chrome. `children` lets the error boundary use it when the shell itself fails. */
export function BareLayout({ children }: { children?: ReactNode }) {
  return (
    <div data-testid="layout-bare" className="flex min-h-dvh items-center justify-center bg-background p-6 text-foreground">
      <main id="main" tabIndex={-1} className="w-full max-w-md focus:outline-none">
        {children ?? <Outlet />}
      </main>
    </div>
  );
}
