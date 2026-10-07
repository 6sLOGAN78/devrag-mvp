import type { ReactNode } from "react";
import { Outlet } from "react-router";
import { LanguageSwitch } from "@/components/language-switch";
import { ThemeToggle } from "@/components/theme-toggle";

/**
 * No navigation chrome. `children` (even null) replaces the Outlet, so a guard can show a blank shell without ever
 * rendering the route. Only the routed form carries the corner cluster, so a signed-out visitor can change language
 * and theme while the guard's own skeleton and error shells stay blank.
 */
export function BareLayout({ children }: { children?: ReactNode }) {
  const routed = children === undefined;
  return (
    <div data-testid="layout-bare" className="relative flex min-h-dvh items-center justify-center bg-background p-6 text-foreground">
      {routed ? (
        <div className="absolute right-4 top-4 flex items-center gap-2">
          <LanguageSwitch />
          <ThemeToggle />
        </div>
      ) : null}
      <main id="main" tabIndex={-1} className="w-full max-w-md focus:outline-none">
        {routed ? <Outlet /> : children}
      </main>
    </div>
  );
}
