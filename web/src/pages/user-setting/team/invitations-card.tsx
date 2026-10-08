import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AvatarInitials } from "@/components/avatar-initials";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRespondToInvitation } from "@/hooks/use-team-request";
import { notifySuccess } from "@/services/notify";
import type { Membership } from "@/services/team-service";
import { isGone, notifyTeamFailure } from "./errors";
import { formatDate } from "./format";

interface InvitationRowProps {
  invitation: Membership;
  /** Called once the invitation is answered (or found gone) so the page can place focus. */
  onAnswered: () => void;
}

/** One invitation. The ids sent are the tenant id the server listed; both buttons are disabled while a request runs. */
function InvitationRow({ invitation, onAnswered }: InvitationRowProps) {
  const { t, i18n } = useTranslation();
  const respond = useRespondToInvitation();
  const busy = respond.isPending;
  const invited = formatDate(invitation.joinedTime, i18n.language);

  async function answer(action: "accept" | "decline"): Promise<void> {
    if (busy) return;
    try {
      await respond.mutateAsync({ tenantId: invitation.tenantId, action });
      if (action === "accept") notifySuccess(t("team.joined", { workspace: invitation.tenantName }));
      else notifySuccess(t("team.declined"));
      onAnswered();
    } catch (error) {
      notifyTeamFailure(error, "respond");
      if (isGone(error)) onAnswered();
    }
  }

  return (
    <li data-testid="invitation-row" className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <AvatarInitials avatar={invitation.ownerAvatar} nickname={invitation.ownerNickname} email="" />
        <div className="flex min-w-0 flex-col">
          <span className="break-words text-sm font-semibold">{t("team.invitedYou", { owner: invitation.ownerNickname, workspace: invitation.tenantName })}</span>
          {invited === null ? null : (
            <time dateTime={invited.iso} className="text-xs font-normal text-muted-foreground">
              {t("team.invitedOn", { date: invited.text })}
            </time>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          data-testid="invitation-accept"
          aria-label={t("team.acceptFrom", { owner: invitation.ownerNickname })}
          aria-busy={busy && respond.variables?.action === "accept" ? true : undefined}
          disabled={busy}
          onClick={() => void answer("accept")}
        >
          {busy && respond.variables?.action === "accept" ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
          {t("team.accept")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          data-testid="invitation-decline"
          aria-label={t("team.declineFrom", { owner: invitation.ownerNickname })}
          aria-busy={busy && respond.variables?.action === "decline" ? true : undefined}
          disabled={busy}
          onClick={() => void answer("decline")}
        >
          {busy && respond.variables?.action === "decline" ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
          {t("team.decline")}
        </Button>
      </div>
    </li>
  );
}

/** "Invitations for you" (UI-36). Rendered by the page only when the caller has at least one pending invitation. */
export function InvitationsCard({ invitations, onAnswered }: { invitations: readonly Membership[]; onAnswered: () => void }) {
  const { t } = useTranslation();
  return (
    <Card data-testid="invitations-for-you">
      <CardHeader>
        <CardTitle>{t("team.invitationsForYou")}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <ul className="divide-y">
          {invitations.map((invitation) => (
            <InvitationRow key={invitation.tenantId} invitation={invitation} onAnswered={onAnswered} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
