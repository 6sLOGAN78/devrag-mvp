import { logoutPath, userInfoPath, userPasswordPath, userSettingPath } from "@/constants/api-paths";
import type { SessionUser, UserInfoDto } from "@/interfaces/user";
import { expectRecord, request } from "./http";

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
  const dto = await request<unknown>({ url: userInfoPath, method: "GET" }, { silent: true });
  return toSessionUser(expectRecord<UserInfoDto>(dto, "user info", ["id"]));
}

/** Invalidates the shared token server-side. Silent so a failed sign out never stacks a toast on the redirect. */
export async function logout(): Promise<void> {
  await request<null>({ url: logoutPath, method: "POST" }, { silent: true });
}

/** The only profile fields the browser may set (POST /v1/user/setting). Anything else is never sent. */
export interface SettingInput {
  nickname?: string;
  /** A data URL produced by the avatar helper, or "" to remove the avatar. */
  avatar?: string;
  language?: "en" | "zh";
  color_schema?: "Bright" | "Dark";
}

/** Silent: callers show their own inline message, or none at all for the best-effort language and theme writes. */
export async function updateSetting(input: SettingInput): Promise<void> {
  await request<unknown>({ url: userSettingPath, method: "POST", data: input }, { silent: true });
}

/**
 * Changes the signed-in user's password (POST /v1/user/setting/password). The values travel once in the JSON body;
 * a wrong current password is HTTP 400, never 401, so the session is not purged by a typo. Silent: the form
 * shows the message inline.
 */
export async function changePassword(current: string, replacement: string): Promise<void> {
  await request<unknown>({ url: userPasswordPath, method: "POST", data: { old_password: current, new_password: replacement } }, { silent: true });
}
