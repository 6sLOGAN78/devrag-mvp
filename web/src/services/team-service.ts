import { tenantListPath, tenantPath, tenantUserPath, tenantUsersPath } from "@/constants/api-paths";
import { request } from "./http";

/** One entry of the caller's workspace list. Role `invite` is a pending invitation, never a role to display. */
export interface Membership {
  tenantId: string;
  tenantName: string;
  ownerNickname: string;
  ownerAvatar: string;
  role: string;
  /** ISO 8601, or empty when the server sent none. */
  joinedTime: string;
}

/** One person in a workspace. Role `invite` marks a pending invitation (owner view only). */
export interface Member {
  id: string;
  nickname: string;
  email: string;
  avatar: string;
  role: string;
  joinedTime: string;
}

interface MembershipDto {
  tenant_id: string;
  tenant_name: string;
  owner_nickname: string;
  owner_avatar: string;
  role: string;
  joined_time: string;
}

interface MemberDto {
  id: string;
  nickname: string;
  email: string;
  avatar: string;
  role: string;
  joined_time: string;
}

/** Roles the owner may assign. `owner` and `invite` are never offered. */
export type AssignableRole = "admin" | "normal";

export type InviteAction = "accept" | "decline";

const text = (value: unknown): string => (typeof value === "string" ? value : "");

function toMembership(dto: MembershipDto): Membership {
  return {
    tenantId: text(dto.tenant_id),
    tenantName: text(dto.tenant_name),
    ownerNickname: text(dto.owner_nickname),
    ownerAvatar: text(dto.owner_avatar),
    role: text(dto.role),
    joinedTime: text(dto.joined_time),
  };
}

function toMember(dto: MemberDto): Member {
  return {
    id: text(dto.id),
    nickname: text(dto.nickname),
    email: text(dto.email),
    avatar: text(dto.avatar),
    role: text(dto.role),
    joinedTime: text(dto.joined_time),
  };
}

/** GET /v1/tenant/list. Silent: each card renders its own error state. */
export async function listMemberships(): Promise<Membership[]> {
  const rows = await request<MembershipDto[]>({ url: tenantListPath, method: "GET" }, { silent: true });
  return Array.isArray(rows) ? rows.map(toMembership) : [];
}

/** GET members of the workspace the server listed. The owner also receives pending invitations (role `invite`). */
export async function listMembers(tenantId: string): Promise<Member[]> {
  const rows = await request<MemberDto[]>({ url: tenantUsersPath(tenantId), method: "GET" }, { silent: true });
  return Array.isArray(rows) ? rows.map(toMember) : [];
}

/** POST invite by email. Silent: the form shows the server message in its own alert. */
export async function inviteMember(tenantId: string, email: string): Promise<Member> {
  return toMember(await request<MemberDto>({ url: tenantUsersPath(tenantId), method: "POST", data: { email } }, { silent: true }));
}

/** PATCH accept or decline the caller's own invitation. */
export async function respondToInvitation(tenantId: string, action: InviteAction): Promise<void> {
  await request<null>({ url: tenantPath(tenantId), method: "PATCH", data: { action } }, { silent: true });
}

/** PATCH role change (owner only). */
export async function changeMemberRole(tenantId: string, userId: string, role: AssignableRole): Promise<void> {
  await request<null>({ url: tenantUserPath(tenantId, userId), method: "PATCH", data: { role } }, { silent: true });
}

/** DELETE remove a member, withdraw an invitation (owner) or leave (the caller's own id). */
export async function removeMember(tenantId: string, userId: string): Promise<void> {
  await request<null>({ url: tenantUsersPath(tenantId), method: "DELETE", data: { user_id: userId } }, { silent: true });
}
