import { ChevronRight } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { PageHeader } from "@/components/page-header";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useApiTokensRequest } from "@/hooks/use-api-token-request";
import { useMembersRequest, useMembershipsRequest } from "@/hooks/use-team-request";
import { useUserStore } from "@/stores/user-store";
import { FOCUS_RING, StatCard } from "./stat-card";

/** The server stores `owner`, `admin` and `normal`; anything that is not an elevated role reads as Member. */
function roleKey(role: string): string {
  if (role === "owner") return "role.owner";
  if (role === "admin") return "role.admin";
  return "role.member";
}

/** The API tokens stat (UI-35). Only the workspace owner manages tokens, so the parent renders this card for the owner alone. */
function TokensStatCard() {
  const { t } = useTranslation();
  const tokens = useApiTokensRequest();
  return (
    <StatCard
      testId="stat-tokens"
      caption={t("home.stat.tokens")}
      to="/user-setting/api"
      isPending={tokens.isPending}
      isError={tokens.isError}
      onRetry={() => void tokens.refetch()}
      value={tokens.data?.length ?? 0}
    />
  );
}

/** Team members: people in the caller's own workspace. Pending invitations the owner has sent are not people. */
function MembersStatCard({ tenantId }: { tenantId: string }) {
  const { t } = useTranslation();
  const members = useMembersRequest(tenantId);
  return (
    <StatCard
      testId="stat-members"
      caption={t("home.stat.members")}
      to="/user-setting/team"
      isPending={members.isPending}
      isError={members.isError}
      onRetry={() => void members.refetch()}
      value={members.data?.filter((member) => member.role !== "invite").length ?? 0}
    />
  );
}

/** Pending invitations waiting for this user to answer (role `invite` in their workspace list). */
function InvitationsStatCard() {
  const { t } = useTranslation();
  const memberships = useMembershipsRequest();
  return (
    <StatCard
      testId="stat-invitations"
      caption={t("home.stat.invitations")}
      to="/user-setting/team"
      isPending={memberships.isPending}
      isError={memberships.isError}
      onRetry={() => void memberships.refetch()}
      value={memberships.data?.filter((entry) => entry.role === "invite").length ?? 0}
    />
  );
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
 * recovered user; the team member count, the API tokens count and the pending invitations count each come from their
 * real list, each with its own loading and error state. The tokens card and link exist for the workspace owner only,
 * who alone may manage tokens. The "Manage your account" card lists only pages that exist.
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
        <StatCard testId="stat-role" caption={t("home.stat.role")} to="/user-setting/team" value={t(roleKey(user.role))} />
        <MembersStatCard tenantId={user.tenantId} />
        {user.role === "owner" ? <TokensStatCard /> : null}
        <InvitationsStatCard />
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
          {user.role === "owner" ? (
            <Link
              to="/user-setting/api"
              data-testid="home-link-tokens"
              className={`flex min-h-10 items-center justify-between rounded-md text-sm font-normal text-primary hover:underline ${FOCUS_RING}`}
            >
              <span>{t("home.links.tokens")}</span>
              <ChevronRight className="size-4 text-muted-foreground" aria-hidden="true" />
            </Link>
          ) : null}
          <Link
            to="/user-setting/team"
            data-testid="home-link-team"
            className={`flex min-h-10 items-center justify-between rounded-md text-sm font-normal text-primary hover:underline ${FOCUS_RING}`}
          >
            <span>{t("home.links.team")}</span>
            <ChevronRight className="size-4 text-muted-foreground" aria-hidden="true" />
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
