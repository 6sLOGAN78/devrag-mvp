import { Outlet } from "react-router";
import { SkipLink } from "@/components/skip-link";
import { ThemeToggle } from "@/components/theme-toggle";
import { useTranslation } from "react-i18next";

export function FullBleedLayout() {
  const { t } = useTranslation();
  return (
    <div data-testid="layout-fullbleed" className="min-h-dvh bg-background text-foreground">
      <SkipLink />
      <header className="flex h-14 items-center justify-between border-b bg-card px-4">
        <span className="text-xl font-semibold leading-tight">{t("app.wordmark")}</span>
        <ThemeToggle />
      </header>
      <main id="main" tabIndex={-1} className="h-[calc(100dvh-56px)] overflow-hidden focus:outline-none">
        <Outlet />
      </main>
    </div>
  );
}
