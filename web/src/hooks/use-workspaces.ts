import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useMembershipsRequest } from "@/hooks/use-team-request";
import { useUserStore } from "@/stores/user-store";
import { buildWorkspaceList, useWorkspaceStore, type Workspace } from "@/stores/workspace-store";

const LOST_TOAST_ID = "workspace-lost";
const LOST_TOAST_MS = 8000;

/**
 * The workspaces the signed-in user can act in: their own first, then the ones they joined as admin or member.
 * Before the list arrives, or if the request fails, only the own workspace is listed; the Team page reports list errors.
 */
export function useWorkspaces(): Workspace[] {
  const { i18n } = useTranslation();
  const user = useUserStore((state) => state.user);
  const memberships = useMembershipsRequest(user !== null).data;
  return useMemo(() => {
    if (user === null) return [];
    const own = { tenantId: user.tenantId, name: user.tenantName, ownerNickname: user.nickname };
    return buildWorkspaceList(own, memberships ?? [], i18n.language);
  }, [user, memberships, i18n.language]);
}

/** The workspace the app currently acts in: the stored choice, else the own workspace; null while signed out. */
export function useActiveWorkspace(): Workspace | null {
  const workspaces = useWorkspaces();
  const activeTenantId = useWorkspaceStore((state) => state.activeTenantId);
  return workspaces.find((workspace) => workspace.tenantId === activeTenantId) ?? workspaces[0] ?? null;
}

/**
 * The tenant id to send as `tenant_id` on workspace-scoped requests that carry no resource id. Plain function so
 * services can call it outside React; the server stays authoritative and answers 404 for a workspace the caller
 * cannot use (T-03-03-01).
 */
export function activeTenantId(): string | null {
  const active = useWorkspaceStore.getState().activeTenantId;
  return active ?? useUserStore.getState().user?.tenantId ?? null;
}

/**
 * Keeps the workspace store in step with the server's membership list and reports a lost workspace once.
 * Mount exactly once, in the always-present header selector.
 */
export function useWorkspaceSync(): void {
  const { t } = useTranslation();
  const user = useUserStore((state) => state.user);
  const memberships = useMembershipsRequest(user !== null).data;
  const lost = useWorkspaceStore((state) => state.lost);

  useEffect(() => {
    if (user === null || memberships === undefined) return;
    const state = useWorkspaceStore.getState();
    if (state.initialisedFor !== user.id || state.ownTenantId !== user.tenantId) state.initialise(user.id, user.tenantId, memberships);
    else state.setMemberships(memberships);
  }, [user, memberships]);

  useEffect(() => {
    if (lost === null) return;
    toast.info(t("workspace.lost.title", { workspace: lost }), {
      id: LOST_TOAST_ID,
      description: t("workspace.lost.body"),
      duration: LOST_TOAST_MS,
      closeButton: true,
    });
    useWorkspaceStore.getState().clearLost();
  }, [lost, t]);
}
