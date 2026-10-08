import { Loader2, UserMinus } from "lucide-react";
import type { Ref } from "react";
import { useTranslation } from "react-i18next";
import { AvatarInitials } from "@/components/avatar-initials";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AssignableRole, Member } from "@/services/team-service";
import { formatDate } from "./format";
import { ASSIGNABLE_ROLES, isAssignable, roleLabelKey } from "./roles";

interface MembersTableProps {
  /** People only; pending invitations are listed elsewhere and never as a role. */
  members: readonly Member[];
  /** True only for the workspace owner. The server remains the authority; this decides what is drawn. */
  canManage: boolean;
  captionRef: Ref<HTMLTableCaptionElement>;
  busyId: string | null;
  onRoleChange: (member: Member, role: AssignableRole, opener: HTMLElement) => void;
  onRemove: (member: Member, opener: HTMLElement) => void;
}

function RoleCell({ member, canManage, onRoleChange }: { member: Member; canManage: boolean; onRoleChange: MembersTableProps["onRoleChange"] }) {
  const { t } = useTranslation();
  if (!canManage || !isAssignable(member.role)) return <Badge variant="outline">{t(roleLabelKey(member.role))}</Badge>;
  // Controlled by the listed role: choosing another value only opens the confirmation, the value stays until the list says otherwise.
  return (
    <NativeSelect
      data-testid="member-role-select"
      aria-label={t("team.roleFor", { nickname: member.nickname })}
      value={member.role}
      onChange={(event) => {
        const next = event.target.value;
        if (isAssignable(next) && next !== member.role) onRoleChange(member, next, event.currentTarget);
      }}
    >
      {ASSIGNABLE_ROLES.map((role) => (
        <option key={role} value={role}>
          {t(roleLabelKey(role))}
        </option>
      ))}
    </NativeSelect>
  );
}

/** Semantic members table (UI-SPEC "Team"): the owner row is a static badge with no action (D-16). */
export function MembersTable({ members, canManage, captionRef, busyId, onRoleChange, onRemove }: MembersTableProps) {
  const { t, i18n } = useTranslation();
  return (
    <Table data-testid="members-table">
      <TableCaption ref={captionRef} tabIndex={-1}>
        {t("team.members.caption")}
      </TableCaption>
      <TableHeader>
        <TableRow className="h-10">
          <TableHead>{t("team.col.member")}</TableHead>
          <TableHead>{t("team.col.role")}</TableHead>
          <TableHead>{t("team.col.joined")}</TableHead>
          <TableHead>{t("team.col.actions")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((member) => {
          const joined = formatDate(member.joinedTime, i18n.language);
          return (
            <TableRow key={member.id} data-testid="member-row">
              <TableCell>
                <div className="flex items-center gap-3">
                  <AvatarInitials avatar={member.avatar} nickname={member.nickname} email={member.email} />
                  <div className="flex min-w-0 flex-col">
                    <span className="break-words text-sm font-semibold">{member.nickname}</span>
                    <span className="break-all text-xs font-normal text-muted-foreground">{member.email}</span>
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <RoleCell member={member} canManage={canManage} onRoleChange={onRoleChange} />
              </TableCell>
              <TableCell className="whitespace-nowrap">{joined === null ? "-" : <time dateTime={joined.iso}>{joined.text}</time>}</TableCell>
              <TableCell>
                {canManage && member.role !== "owner" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    data-testid="member-remove"
                    aria-label={t("team.remove.label", { nickname: member.nickname })}
                    aria-busy={busyId === member.id ? true : undefined}
                    className="hover:text-destructive focus-visible:text-destructive"
                    onClick={(event) => onRemove(member, event.currentTarget)}
                  >
                    {busyId === member.id ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <UserMinus aria-hidden="true" />}
                  </Button>
                ) : null}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
