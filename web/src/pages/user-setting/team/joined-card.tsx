import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLeaveWorkspace } from "@/hooks/use-team-request";
import { notifySuccess } from "@/services/notify";
import type { Membership } from "@/services/team-service";
import { ConfirmDialog } from "./confirm-dialog";
import { isGone, notifyTeamFailure } from "./errors";
import { roleLabelKey } from "./roles";

interface JoinedCardProps {
  workspaces: readonly Membership[];
  /** The signed-in user's id, as the server returned it at sign in. It is the only id a leave request carries. */
  userId: string;
  /** Called after a workspace is left (or found gone) so the page can move focus somewhere that still exists. */
  onLeft: () => void;
}

/**
 * "Workspaces you've joined" (UI-36): name, owner, the caller's role and Leave. The page passes only workspaces the
 * caller does not own, so the caller's own workspace never offers Leave (D-16). The tenant id comes from the row.
 */
export function JoinedCard({ workspaces, userId, onLeft }: JoinedCardProps) {
  const { t } = useTranslation();
  const leave = useLeaveWorkspace();
  const [target, setTarget] = useState<Membership | null>(null);
  const left = useRef(false);
  const opener = useRef<HTMLElement | null>(null);

  async function confirm(): Promise<void> {
    if (target === null || leave.isPending) return;
    try {
      await leave.mutateAsync({ tenantId: target.tenantId, userId });
      notifySuccess(t("team.leave.done", { workspace: target.tenantName }));
      left.current = true;
    } catch (error) {
      notifyTeamFailure(error, "leave");
      if (isGone(error)) left.current = true;
    }
    setTarget(null);
    if (left.current) onLeft();
  }

  return (
    <Card data-testid="joined-workspaces">
      <CardHeader>
        <CardTitle>{t("team.joinedWorkspaces")}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <ul className="divide-y">
          {workspaces.map((workspace) => (
            <li key={workspace.tenantId} data-testid="joined-row" className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 flex-col">
                <span className="break-words text-sm font-semibold">{workspace.tenantName}</span>
                <span className="break-words text-xs font-normal text-muted-foreground">{t("team.ownedBy", { owner: workspace.ownerNickname })}</span>
              </div>
              <div className="flex items-center gap-3">
                <Badge variant="outline">{t(roleLabelKey(workspace.role))}</Badge>
                <Button
                  type="button"
                  variant="outline"
                  data-testid="workspace-leave"
                  aria-label={t("team.leave.label", { workspace: workspace.tenantName })}
                  onClick={(event) => {
                    left.current = false;
                    opener.current = event.currentTarget;
                    setTarget(workspace);
                  }}
                >
                  {t("team.leave.action")}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(open) => {
          if (!open) setTarget(null);
        }}
        title={t("team.leave.title", { workspace: target?.tenantName ?? "" })}
        description={t("team.leave.body", { workspace: target?.tenantName ?? "" })}
        keepLabel={t("team.leave.keep")}
        confirmLabel={t("team.leave.confirm")}
        destructive
        pending={leave.isPending}
        onConfirm={() => void confirm()}
        opener={opener}
        keepFocusElsewhere={() => left.current}
      />
    </Card>
  );
}
