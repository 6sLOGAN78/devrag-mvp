import { useEffect, useRef, useState, type Ref } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useLastDefined } from "@/hooks/use-last-defined";
import { useChangeMemberRole, useMembersRequest, useRemoveMember } from "@/hooks/use-team-request";
import type { SessionUser } from "@/interfaces/user";
import { notifySuccess } from "@/services/notify";
import type { AssignableRole, Member } from "@/services/team-service";
import { ConfirmDialog } from "./confirm-dialog";
import { isGone, notifyTeamFailure } from "./errors";
import { InviteForm } from "./invite-form";
import { MembersTable } from "./members-table";
import { PendingList } from "./pending-list";
import { roleArticleKey } from "./roles";

function MembersSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="members-skeleton" className="flex flex-col gap-2 p-4">
      <p role="status" className="sr-only">
        {t("team.loading")}
      </p>
      <Skeleton className="h-10 w-full" aria-hidden="true" />
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} className="h-12 w-full" aria-hidden="true" />
      ))}
    </div>
  );
}

type Pending = { kind: "role"; member: Member; role: AssignableRole } | { kind: "remove"; member: Member } | { kind: "withdraw"; member: Member };

/**
 * "Your workspace" (UI-36): header with the workspace name and an i18n plural member count, the owner-only invite
 * form, the members table and the owner-only list of invitations sent. Every id sent comes from a listed row or the
 * session user; the tenant id is the caller's own workspace, never read from the URL. Role change, remove and
 * withdraw each confirm first; none is optimistic: the lists are refetched when a request settles.
 */
export function WorkspaceCard({ user, cardRef }: { user: SessionUser; cardRef: Ref<HTMLDivElement> }) {
  const { t } = useTranslation();
  const tenantId = user.tenantId;
  const isOwner = user.role === "owner";
  const members = useMembersRequest(tenantId);
  const changeRole = useChangeMemberRole(tenantId);
  const remove = useRemoveMember(tenantId);
  const [pending, setPending] = useState<Pending | null>(null);
  const [focusRequest, setFocusRequest] = useState(0);
  const caption = useRef<HTMLTableCaptionElement>(null);
  const gone = useRef(false);
  const opener = useRef<HTMLElement | null>(null);

  // After a row is removed the control that opened the dialog no longer exists: focus moves to the table caption.
  useEffect(() => {
    if (focusRequest === 0) return;
    caption.current?.focus();
  }, [focusRequest]);

  const rows = members.data ?? [];
  const people = rows.filter((member) => member.role !== "invite");
  const invitations = rows.filter((member) => member.role === "invite");
  const busyId = remove.isPending ? (remove.variables ?? null) : null;

  async function confirm(): Promise<void> {
    if (pending === null) return;
    const current = pending;
    if (current.kind === "role") {
      if (changeRole.isPending) return;
      try {
        await changeRole.mutateAsync({ userId: current.member.id, role: current.role });
        notifySuccess(t("team.role.updated"));
      } catch (error) {
        notifyTeamFailure(error, "role");
      }
      setPending(null);
      return;
    }
    if (remove.isPending) return;
    const withdraw = current.kind === "withdraw";
    try {
      await remove.mutateAsync(current.member.id);
      notifySuccess(withdraw ? t("team.withdraw.done") : t("team.remove.done"));
      gone.current = true;
    } catch (error) {
      notifyTeamFailure(error, withdraw ? "withdraw" : "remove");
      if (isGone(error)) gone.current = true;
    }
    setPending(null);
    if (gone.current) setFocusRequest((count) => count + 1);
  }

  function ask(next: Pending, from: HTMLElement): void {
    gone.current = false;
    opener.current = from;
    setPending(next);
  }

  let body;
  if (members.isPending) {
    body = <MembersSkeleton />;
  } else if (members.isError) {
    body = (
      <div className="p-6">
        <ErrorState noun={t("team.errorNoun.members")} onAction={() => void members.refetch()} />
      </div>
    );
  } else {
    body = (
      <>
        <MembersTable
          members={people}
          canManage={isOwner}
          captionRef={caption}
          busyId={busyId}
          onRoleChange={(member, role, from) => ask({ kind: "role", member, role }, from)}
          onRemove={(member, from) => ask({ kind: "remove", member }, from)}
        />
        {people.length <= 1 ? <p className="py-6 text-center text-sm font-normal text-muted-foreground">{t("team.noTeammates")}</p> : null}
      </>
    );
  }

  const shown = useLastDefined(pending);
  const dialog = describe(shown, user.tenantName, t);
  return (
    <Card ref={cardRef} tabIndex={-1} data-testid="workspace-card" className="focus-visible:outline-none">
      <CardHeader>
        <CardTitle>{t("team.workspace.title")}</CardTitle>
        <p className="flex flex-wrap items-baseline gap-x-2 text-sm font-normal text-muted-foreground">
          <span data-testid="workspace-name" className="break-words font-semibold text-foreground">
            {user.tenantName}
          </span>
          {members.data === undefined ? null : <span data-testid="member-count">{t("team.members.count", { count: people.length })}</span>}
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-6 p-0 pb-6">
        {isOwner ? (
          <div className="px-6">
            <InviteForm tenantId={tenantId} />
          </div>
        ) : null}
        {body}
        {isOwner && members.data !== undefined ? (
          <div className="px-6">
            <PendingList invitations={invitations} onWithdraw={(member, from) => ask({ kind: "withdraw", member }, from)} />
          </div>
        ) : null}
      </CardContent>
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
        title={dialog.title}
        description={dialog.description}
        keepLabel={dialog.keep}
        confirmLabel={dialog.confirm}
        destructive={shown?.kind !== "role"}
        pending={changeRole.isPending || remove.isPending}
        onConfirm={() => void confirm()}
        opener={opener}
        keepFocusElsewhere={() => gone.current}
      />
    </Card>
  );
}

function describe(pending: Pending | null, workspace: string, t: (key: string, options?: Record<string, unknown>) => string) {
  if (pending === null) return { title: "", description: "", keep: "", confirm: "" };
  const { member } = pending;
  if (pending.kind === "role") {
    const role = t(roleArticleKey(pending.role));
    return {
      title: t("team.role.title", { nickname: member.nickname }),
      description: t("team.role.body", { nickname: member.nickname, role, workspace }),
      keep: t("team.role.keep"),
      confirm: t("team.role.confirm"),
    };
  }
  if (pending.kind === "remove") {
    return {
      title: t("team.remove.title", { nickname: member.nickname }),
      description: t("team.remove.body", { nickname: member.nickname, workspace }),
      keep: t("team.remove.keep"),
      confirm: t("team.remove.confirm"),
    };
  }
  return {
    title: t("team.withdraw.title"),
    description: t("team.withdraw.body", { email: member.email, workspace }),
    keep: t("team.withdraw.keep"),
    confirm: t("team.withdraw.confirm"),
  };
}
