import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMembershipsRequest } from "@/hooks/use-team-request";
import { useUserStore } from "@/stores/user-store";
import { InvitationsCard } from "./invitations-card";
import { JoinedCard } from "./joined-card";
import { WorkspaceCard } from "./workspace-card";

/**
 * Team page (UI-36). Three cards in a fixed order: invitations for the caller (only when pending), the caller's own
 * workspace, and workspaces the caller joined (only when there are any). Invitations and joined workspaces both come
 * from the caller's workspace list; the role `invite` is the pending state and is never shown as a role. Other
 * people's names, emails and workspace names are rendered as text only.
 */
export default function TeamPage() {
  const { t, i18n } = useTranslation();
  const user = useUserStore((state) => state.user);
  const memberships = useMembershipsRequest();
  const workspace = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = t("team.pageTitle");
  }, [t, i18n.language]);

  if (user === null) {
    return (
      <div data-testid="team-page" className="flex flex-col gap-6">
        <PageHeader title={t("team.title")} />
        <Skeleton className="h-40 w-full" aria-hidden="true" />
      </div>
    );
  }

  const list = memberships.data ?? [];
  const invitations = list.filter((entry) => entry.role === "invite");
  const joined = list.filter((entry) => entry.role !== "invite" && entry.tenantId !== user.tenantId);
  // The row the user acted on is gone: focus goes to a card that still exists.
  const focusWorkspace = () => workspace.current?.focus();

  return (
    <div data-testid="team-page" className="flex flex-col gap-6">
      <PageHeader title={t("team.title")} />
      <p className="max-w-prose text-sm font-normal text-muted-foreground">{t("team.intro")}</p>
      {memberships.isError ? (
        <Card>
          <CardContent className="p-6">
            <ErrorState noun={t("team.errorNoun.invitations")} onAction={() => void memberships.refetch()} />
          </CardContent>
        </Card>
      ) : null}
      {invitations.length > 0 ? <InvitationsCard invitations={invitations} onAnswered={focusWorkspace} /> : null}
      <WorkspaceCard user={user} cardRef={workspace} />
      {joined.length > 0 ? <JoinedCard workspaces={joined} userId={user.id} onLeft={focusWorkspace} /> : null}
    </div>
  );
}
