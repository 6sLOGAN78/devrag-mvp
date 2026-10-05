import { Menu } from "lucide-react";
import { useState } from "react";
import { Outlet } from "react-router";
import { AppSidebar } from "@/components/app-sidebar";
import { SkipLink } from "@/components/skip-link";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { TooltipProvider } from "@/components/ui/tooltip";
import { copy } from "@/constants/copy";

export function StandardLayout() {
  const [open, setOpen] = useState(false);
  return (
    <TooltipProvider delayDuration={200}>
      <div data-testid="layout-standard" className="flex h-dvh flex-col bg-background text-foreground">
        <SkipLink />
        <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card px-4">
          <div className="flex items-center gap-2">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="md:hidden" aria-label={copy.nav.openMenu}>
                  <Menu />
                </Button>
              </SheetTrigger>
              <SheetContent>
                <SheetHeader>
                  <SheetTitle>{copy.app.wordmark}</SheetTitle>
                  <SheetDescription className="sr-only">{copy.a11y.primaryNav}</SheetDescription>
                </SheetHeader>
                <div className="mt-4">
                  <AppSidebar forceLabels onNavigate={() => setOpen(false)} />
                </div>
              </SheetContent>
            </Sheet>
            <span className="text-xl font-semibold leading-tight">{copy.app.wordmark}</span>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
          </div>
        </header>
        <div data-testid="app-shell" className="flex min-h-0 flex-1">
          <aside className="hidden w-16 shrink-0 border-r bg-card p-2 md:block lg:w-60 lg:p-4">
            <AppSidebar />
          </aside>
          <main id="main" tabIndex={-1} className="min-w-0 flex-1 overflow-auto p-6 focus:outline-none xl:p-8">
            <div className="mx-auto max-w-screen-xl">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
