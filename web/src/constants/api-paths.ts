import routeTable from "./api-routes.generated.json";

interface GeneratedRoute {
  owner: "go" | "python";
  match: "exact" | "prefix";
  path: string;
}

/** Looks a path up in the generated route table (from conf/routes.yaml); a miss is a build-time bug. */
function resolve(owner: GeneratedRoute["owner"], path: string): string {
  const found = (routeTable.routes as GeneratedRoute[]).find((r) => r.owner === owner && r.match === "exact" && r.path === path);
  if (!found) throw new Error(`route ${path} (${owner}) is not in api-routes.generated.json`);
  return found.path;
}

/** Same lookup for a prefix route; `rest` is the concrete path under it. */
function resolveUnder(owner: GeneratedRoute["owner"], prefix: string, rest: string): string {
  const found = (routeTable.routes as GeneratedRoute[]).find((r) => r.owner === owner && r.match === "prefix" && r.path === prefix);
  if (!found) throw new Error(`prefix route ${prefix} (${owner}) is not in api-routes.generated.json`);
  return `${found.path}${rest}`;
}

// The lookup keys below are the registry entries; components import only the resolved constants.
export const goHealthPath = resolve("go", "/health");
export const pythonStatusPath = resolve("python", "/api/v1/system/status");
export const logoutPath = resolve("go", "/api/v1/auth/logout");
export const userInfoPath = resolveUnder("go", "/v1/user/", "info");
export const userSettingPath = resolveUnder("go", "/v1/user/", "setting");
export const userPasswordPath = resolveUnder("go", "/v1/user/", "setting/password");
export const loginPath = resolveUnder("go", "/api/v1/auth/", "login");
export const registerPath = resolve("go", "/api/v1/users");
export const systemConfigPath = resolve("go", "/api/v1/system/config");
export const forgotOtpPath = resolveUnder("go", "/api/v1/auth/", "password/forgot/otp");
export const forgotOtpVerifyPath = resolveUnder("go", "/api/v1/auth/", "password/forgot/otp/verify");
export const passwordResetPath = resolveUnder("go", "/api/v1/auth/", "password/reset");

/** API token management (GET list, POST create) and the per-token DELETE path under it. Owner session only. */
export const apiTokensPath = resolve("go", "/api/v1/system/tokens");
/** DELETE path for one token. The value is percent-encoded; it appears in this path only, never in the page URL. */
export function apiTokenPath(token: string): string {
  return resolveUnder("go", "/api/v1/system/tokens/", encodeURIComponent(token));
}
