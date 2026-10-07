/** GET /v1/user/info as the Go engine returns it (internal/handler/user.go UserInfoDTO). */
export interface UserInfoDto {
  id: string;
  nickname: string;
  email: string;
  avatar: string;
  language: string;
  color_schema: string;
  tenant_id: string;
  tenant_name: string;
  role: string;
  is_superuser: boolean;
}

/** The recovered signed-in user held in the user store. It never carries a token. */
export interface SessionUser {
  id: string;
  nickname: string;
  email: string;
  avatar: string;
  language: string;
  colorSchema: string;
  tenantId: string;
  tenantName: string;
  role: string;
  isSuperuser: boolean;
}
