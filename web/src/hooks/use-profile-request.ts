import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useNavigate } from "react-router";
import i18n from "@/i18n";
import type { SessionUser } from "@/interfaces/user";
import { purgeSession } from "@/services/http";
import { notifySuccess } from "@/services/notify";
import { changePassword, updateSetting, type SettingInput } from "@/services/user-service";
import { useUserStore } from "@/stores/user-store";
import { beginSignOut, endSignOut } from "@/utils/sign-out-intent";
import { USER_INFO_QUERY_KEY } from "./use-user-info-request";

/** The profile card edits exactly these two fields; language and theme go through `saveSettingQuietly`. */
export type ProfileEdit = Pick<SettingInput, "nickname" | "avatar">;

/**
 * Saves the edited profile fields (POST /v1/user/setting). On success the user store and the cached session user are
 * updated, so the header menu and the welcome title change without a reload. Only the fields that were edited are sent.
 */
export function useProfileRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (edit: ProfileEdit) => {
      await updateSetting(edit);
      return edit;
    },
    onSuccess: (edit) => {
      const apply = (user: SessionUser): SessionUser => ({
        ...user,
        ...(edit.nickname === undefined ? {} : { nickname: edit.nickname }),
        ...(edit.avatar === undefined ? {} : { avatar: edit.avatar }),
      });
      const current = useUserStore.getState().user;
      if (current !== null) useUserStore.getState().setUser(apply(current));
      queryClient.setQueryData<SessionUser>(USER_INFO_QUERY_KEY, (cached) => (cached === undefined ? cached : apply(cached)));
    },
  });
}

/**
 * Best-effort write of the language or theme choice to the profile (UI-42, UI-43). It runs only for a signed-in user,
 * is silent, and swallows every failure: the local choice is authoritative and has already been applied.
 */
export async function saveSettingQuietly(input: Pick<SettingInput, "language" | "color_schema">): Promise<void> {
  const before = useUserStore.getState().user;
  if (before === null) return;
  try {
    await updateSetting(input);
  } catch {
    return;
  }
  const after = useUserStore.getState().user;
  if (after === null || after.id !== before.id) return;
  useUserStore.getState().setUser({
    ...after,
    ...(input.language === undefined ? {} : { language: input.language }),
    ...(input.color_schema === undefined ? {} : { colorSchema: input.color_schema }),
  });
}

/**
 * Changes the password and, on success, ends this browser's session (D-08): the server has already invalidated the
 * token everywhere, so the local token, user and query cache are purged without the "Session expired" toast, the
 * browser goes to a bare /login, and "Password changed" is shown instead.
 *
 * A plain async function on purpose, not a TanStack mutation: a mutation would keep its variables, and so the
 * passwords, in the mutation cache. A rejection (wrong current password is HTTP 400) rejects here and leaves the
 * session untouched.
 */
export function usePasswordChange() {
  const navigate = useNavigate();
  return useCallback(
    async (current: string, replacement: string): Promise<void> => {
      await changePassword(current, replacement);
      beginSignOut();
      purgeSession({ toast: false, navigate: false });
      notifySuccess(i18n.t("auth.passwordChanged.title"), i18n.t("auth.passwordChanged.body"));
      try {
        await navigate("/login", { replace: true });
      } finally {
        endSignOut();
      }
    },
    [navigate],
  );
}
