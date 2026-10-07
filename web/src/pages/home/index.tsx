import { ChevronRight } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
 * empty tile or dead link is rendered here. The "Manage your account" card lists only pages that exist: the profile
 * row now, the API tokens and team rows when their pages are built.
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
      <Card data-testid="home-links">
        <CardHeader>
          <CardTitle>{t("home.links.title")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col">
          <Link
            to="/user-setting/profile"
            data-testid="home-link-profile"
            className="flex min-h-10 items-center justify-between rounded-md text-sm font-normal text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <span>{t("home.links.profile")}</span>
            <ChevronRight className="size-4 text-muted-foreground" aria-hidden="true" />
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
