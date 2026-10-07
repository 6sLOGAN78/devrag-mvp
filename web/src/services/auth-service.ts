import { loginPath, registerPath } from "@/constants/api-paths";
import { ApiError, request } from "./http";

interface LoginData {
  token?: unknown;
}

/**
 * Sign in. The password travels once, in the JSON body over the same-origin ingress, exactly as the Go endpoint
 * reads it (`{ email, password }`, internal/handler/account.go). Silent so the inline Alert is the only message;
 * anonymous so a stale stored token never rides along and a credential failure can never purge a session.
 */
export async function login(email: string, password: string): Promise<{ token: string }> {
  const data = await request<LoginData | null>({ url: loginPath, method: "POST", data: { email, password }, anonymous: true }, { silent: true });
  if (typeof data?.token !== "string" || data.token === "") throw new ApiError({ code: -1, status: 200, message: "" });
  return { token: data.token };
}

/** Create an account and its workspace (POST /api/v1/users). */
export async function register(input: { email: string; password: string; nickname: string }): Promise<void> {
  await request<unknown>({ url: registerPath, method: "POST", data: input, anonymous: true }, { silent: true });
}
