import { Building2, ChevronsUpDown } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useActiveWorkspace, useWorkspaces, useWorkspaceSync } from "@/hooks/use-workspaces";
import { roleLabelKey } from "@/pages/user-setting/team/roles";
import { useWorkspaceStore, type Workspace } from "@/stores/workspace-store";

/**
 * Header selector for the workspace the app acts in (D-26). A user with one workspace sees its name as plain text;
 * a user with several gets a menu. Workspace and owner names are user-supplied and render as text nodes only.
 */
export function WorkspaceSwitch() {
  const { t } = useTranslation();
  useWorkspaceSync();
  const workspaces = useWorkspaces();
  const active = useActiveWorkspace();
  const setActive = useWorkspaceStore((state) => state.setActive);
  const [announcement, setAnnouncement] = useState("");

  if (active === null) return null;

  const choose = (tenantId: string) => {
    if (tenantId === active.tenantId) return;
    const next = workspaces.find((workspace) => workspace.tenantId === tenantId);
    if (next === undefined) return;
    setActive(tenantId);
    setAnnouncement(t("workspace.switched", { workspace: next.name }));
  };

  const roleLine = (workspace: Workspace): string => {
    const role = t(roleLabelKey(workspace.role));
    return workspace.own ? role : t("workspace.roleOwned", { role, owner: workspace.ownerNickname });
  };

  if (workspaces.length < 2) {
    return (
      <span data-testid="workspace-current" className="flex min-w-0 items-center gap-2 px-2 text-sm font-semibold">
        <Building2 aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <span className="sr-only">{t("workspace.prefix")}</span>
        <span className="max-w-24 truncate sm:max-w-[200px]">{active.name}</span>
      </span>
    );
  }

  return (
    <div className="flex min-w-0 items-center">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            className="min-w-0 gap-2 px-2"
            aria-label={t("workspace.label", { name: active.name })}
            data-testid="workspace-switch"
          >
            <Building2 aria-hidden="true" className="text-muted-foreground" />
            <span className="max-w-24 truncate sm:max-w-[200px]">{active.name}</span>
            <ChevronsUpDown aria-hidden="true" className="text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-60">
          <DropdownMenuLabel className="font-semibold text-muted-foreground">{t("workspace.menuCaption")}</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={active.tenantId} onValueChange={choose}>
            {workspaces.map((workspace) => (
              <DropdownMenuRadioItem key={workspace.tenantId} value={workspace.tenantId} data-testid={`workspace-option-${workspace.tenantId}`}>
                <span className="flex min-w-0 flex-col">
                  <span className="truncate">{workspace.name}</span>
                  <span className="truncate text-xs font-normal text-muted-foreground">{roleLine(workspace)}</span>
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link to="/user-setting/team">{t("workspace.manageTeam")}</Link>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <span role="status" className="sr-only" data-testid="workspace-announcer">
        {announcement}
      </span>
    </div>
  );
}
