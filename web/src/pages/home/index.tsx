import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useUserStore } from "@/stores/user-store";

/** The server stores `owner`, `admin` and `normal`; anything that is not an elevated role reads as Member. */
function roleKey(role: string): string {
  if (role === "owner") return "role.owner";
  if (role === "admin") return "role.admin";
  return "role.member";
}

function HomeSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="home-skeleton" className="flex flex-col gap-6">
      <p role="status" className="sr-only">
        {t("home.loading")}
      </p>
      <Skeleton className="h-7 w-64" aria-hidden="true" />
      <Skeleton className="h-4 w-48" aria-hidden="true" />
      <Skeleton className="h-24 w-full sm:w-64" aria-hidden="true" />
    </div>
  );
}

/**
 * Signed-in landing page (UI-09). Real data only: the greeting, the workspace and the caller's role come from the
 * recovered user. Members, tokens and invitations cards arrive with the plans that add those endpoints, so no
 * empty tile or dead link is rendered here.
 */
export default function HomePage() {
  const { t, i18n } = useTranslation();
  const user = useUserStore((state) => state.user);
  useEffect(() => {
    document.title = t("home.pageTitle");
  }, [t, i18n.language]);
  if (user === null) {
    return (
      <div data-testid="home-page">
        <HomeSkeleton />
      </div>
    );
  }
  return (
    <div data-testid="home-page" className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <PageHeader title={t("home.title", { nickname: user.nickname })} />
        <p className="text-sm font-normal text-muted-foreground">{t("home.workspace", { name: user.tenantName })}</p>
      </div>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <Card data-testid="stat-role">
          <CardContent className="flex flex-col gap-1 p-6">
            <span className="text-sm font-semibold text-muted-foreground">{t("home.stat.role")}</span>
            <span className="text-xl font-semibold leading-tight tabular-nums">{t(roleKey(user.role))}</span>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
