import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { Member } from "@/services/team-service";
import { formatDate } from "./format";

/**
 * Owner-only list of invitations this workspace has sent (role `invite` rows). It is the only place a pending
 * invitation appears, and it never shows a role. Withdraw opens a confirmation owned by the workspace card.
 */
export function PendingList({ invitations, onWithdraw }: { invitations: readonly Member[]; onWithdraw: (invitation: Member, opener: HTMLElement) => void }) {
  const { t, i18n } = useTranslation();
  return (
    <section aria-labelledby="pending-sent-title" className="flex flex-col gap-2">
      <h3 id="pending-sent-title" className="text-sm font-semibold">
        {t("team.pending.title")}
      </h3>
      {invitations.length === 0 ? (
        <p data-testid="pending-sent-empty" className="text-sm font-normal text-muted-foreground">
          {t("team.pending.none")}
        </p>
      ) : (
        <ul data-testid="pending-sent-list" className="divide-y rounded-md border">
          {invitations.map((invitation) => {
            const invited = formatDate(invitation.joinedTime, i18n.language);
            return (
              <li key={invitation.id} data-testid="pending-sent-row" className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 flex-col">
                  <span className="break-all text-sm font-semibold">{invitation.email}</span>
                  {invitation.nickname === "" ? null : <span className="break-words text-xs font-normal text-muted-foreground">{invitation.nickname}</span>}
                  {invited === null ? null : (
                    <time dateTime={invited.iso} className="text-xs font-normal text-muted-foreground">
                      {t("team.invitedOn", { date: invited.text })}
                    </time>
                  )}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  data-testid="invitation-withdraw"
                  aria-label={t("team.withdraw.label", { email: invitation.email })}
                  onClick={(event) => onWithdraw(invitation, event.currentTarget)}
                >
                  {t("team.withdraw.action")}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
