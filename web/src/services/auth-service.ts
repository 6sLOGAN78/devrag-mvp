import { forgotOtpPath, forgotOtpVerifyPath, loginPath, passwordResetPath, registerPath } from "@/constants/api-paths";
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

/**
 * Password reset, step 1 (D-07). The server answers every well-formed email the same way, so the resolved value
 * carries nothing and callers must not branch on it. Anonymous and silent: the page owns every message.
 */
export async function requestResetCode(email: string): Promise<void> {
  await request<unknown>({ url: forgotOtpPath, method: "POST", data: { email }, anonymous: true }, { silent: true });
}

/** Password reset, step 2: exchanges the emailed code for a single-use reset ticket. */
export async function verifyResetCode(email: string, otp: string): Promise<{ ticket: string }> {
  const data = await request<{ reset_ticket?: unknown } | null>({ url: forgotOtpVerifyPath, method: "POST", data: { email, otp }, anonymous: true }, { silent: true });
  if (typeof data?.reset_ticket !== "string" || data.reset_ticket === "") throw new ApiError({ code: -1, status: 200, message: "" });
  return { ticket: data.reset_ticket };
}

/** Password reset, step 3: sets the new password with the ticket. Creates no session. */
export async function resetPassword(email: string, ticket: string, newPassword: string): Promise<void> {
  await request<unknown>({ url: passwordResetPath, method: "POST", data: { email, reset_ticket: ticket, new_password: newPassword }, anonymous: true }, { silent: true });
}
