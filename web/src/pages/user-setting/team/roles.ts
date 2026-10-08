import type { AssignableRole } from "@/services/team-service";

/** Locale key of a role's label. `owner`, `admin` and `normal` are the stored roles; anything else reads as Member. */
export function roleLabelKey(role: string): string {
  if (role === "owner") return "role.owner";
  if (role === "admin") return "role.admin";
  return "role.member";
}

/** The two roles the owner may assign; `owner` and `invite` are never offered. */
export const ASSIGNABLE_ROLES: readonly AssignableRole[] = ["admin", "normal"];

export function isAssignable(role: string): role is AssignableRole {
  return role === "admin" || role === "normal";
}

/** Locale key of the role with its English article ("an admin", "a member"); Chinese omits the article. */
export function roleArticleKey(role: AssignableRole): string {
  if (role === "admin") return "team.role.article.admin";
  return "team.role.article.normal";
}
