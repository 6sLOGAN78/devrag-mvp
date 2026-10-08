import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  changeMemberRole,
  inviteMember,
  listMembers,
  listMemberships,
  removeMember,
  respondToInvitation,
  type AssignableRole,
  type InviteAction,
} from "@/services/team-service";

/** Query keys. Names and emails of other people are cached, so `purgeSession` clears them on sign out. */
export const MEMBERSHIPS_QUERY_KEY = ["team", "memberships"] as const;
export const membersQueryKey = (tenantId: string) => ["team", "members", tenantId] as const;

/** The caller's workspaces and pending invitations. No retry: a 4xx is an answer, not a glitch. */
export function useMembershipsRequest(enabled = true) {
  return useQuery({ queryKey: MEMBERSHIPS_QUERY_KEY, queryFn: listMemberships, retry: false, enabled });
}

/** Members of one workspace, keyed by the tenant id the server listed. */
export function useMembersRequest(tenantId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: membersQueryKey(tenantId ?? ""),
    queryFn: () => listMembers(tenantId ?? ""),
    retry: false,
    enabled: enabled && tenantId !== undefined && tenantId !== "",
  });
}

/** Sends an invitation. The members list is refreshed on success. */
export function useInviteMember(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (email: string) => inviteMember(tenantId, email),
    gcTime: 0,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: membersQueryKey(tenantId) }),
  });
}

/** Accepts or declines one invitation. The list is refreshed whatever the outcome, so a withdrawn invitation just disappears. */
export function useRespondToInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { tenantId: string; action: InviteAction }) => respondToInvitation(input.tenantId, input.action),
    gcTime: 0,
    onSettled: () => queryClient.invalidateQueries({ queryKey: MEMBERSHIPS_QUERY_KEY }),
  });
}

/** Changes a role. Not optimistic: the list is refetched when the request settles. */
export function useChangeMemberRole(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { userId: string; role: AssignableRole }) => changeMemberRole(tenantId, input.userId, input.role),
    gcTime: 0,
    onSettled: () => queryClient.invalidateQueries({ queryKey: membersQueryKey(tenantId) }),
  });
}

/** Removes a member or withdraws an invitation in the caller's own workspace. Refetched whatever the outcome. */
export function useRemoveMember(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeMember(tenantId, userId),
    gcTime: 0,
    onSettled: () => queryClient.invalidateQueries({ queryKey: membersQueryKey(tenantId) }),
  });
}

/**
 * Leaves a workspace the caller joined. On success, and on a 404 (already gone), the cached members of that
 * workspace are dropped and the membership list is refetched, so the section disappears.
 */
export function useLeaveWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { tenantId: string; userId: string }) => removeMember(input.tenantId, input.userId),
    gcTime: 0,
    onSettled: (_data, _error, input) => {
      queryClient.removeQueries({ queryKey: membersQueryKey(input.tenantId) });
      return queryClient.invalidateQueries({ queryKey: MEMBERSHIPS_QUERY_KEY });
    },
  });
}
