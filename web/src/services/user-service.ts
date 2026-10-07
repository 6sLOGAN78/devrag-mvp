import { logoutPath, userInfoPath } from "@/constants/api-paths";
import type { SessionUser, UserInfoDto } from "@/interfaces/user";
import { request } from "./http";

function toSessionUser(dto: UserInfoDto): SessionUser {
  return {
    id: dto.id,
    nickname: dto.nickname,
    email: dto.email,
    avatar: dto.avatar,
    language: dto.language,
    colorSchema: dto.color_schema,
    tenantId: dto.tenant_id,
    tenantName: dto.tenant_name,
    role: dto.role,
    isSuperuser: dto.is_superuser,
  };
}

/** Session recovery. Silent: the guard renders its own error state, and a 401 purges through the http client. */
export async function getUserInfo(): Promise<SessionUser> {
  return toSessionUser(await request<UserInfoDto>({ url: userInfoPath, method: "GET" }, { silent: true }));
}

/** Invalidates the shared token server-side. Silent so a failed sign out never stacks a toast on the redirect. */
export async function logout(): Promise<void> {
  await request<null>({ url: logoutPath, method: "POST" }, { silent: true });
}
