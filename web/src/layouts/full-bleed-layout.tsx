import { Outlet } from "react-router";
import { SkipLink } from "@/components/skip-link";
import { ThemeToggle } from "@/components/theme-toggle";
import { copy } from "@/constants/copy";

export function FullBleedLayout() {
  return (
    <div data-testid="layout-fullbleed" className="min-h-dvh bg-background text-foreground">
      <SkipLink />
      <header className="flex h-14 items-center justify-between border-b bg-card px-4">
        <span className="text-xl font-semibold leading-tight">{copy.app.wordmark}</span>
        <ThemeToggle />
      </header>
      <main id="main" tabIndex={-1} className="h-[calc(100dvh-56px)] overflow-hidden focus:outline-none">
        <Outlet />
      </main>
    </div>
  );
}
