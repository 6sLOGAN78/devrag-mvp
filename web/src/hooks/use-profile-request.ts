import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { SessionUser } from "@/interfaces/user";
import { updateSetting, type SettingInput } from "@/services/user-service";
import { useUserStore } from "@/stores/user-store";
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
