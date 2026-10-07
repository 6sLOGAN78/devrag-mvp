import { z } from "zod";
import { newPasswordField } from "@/pages/login/schemas";

/**
 * Change-password form (D-02). The current value has no length rule: an account created under an older rule must
 * still be able to change it. The new value is 8 to 128 characters, length only, never trimmed. There is no confirmation
 * field (UI-SPEC: the show/hide toggle replaces it). Issues are i18n keys.
 */
export const passwordChangeSchema = z.object({
  current: z.string().min(1, "errors.password.required"),
  replacement: newPasswordField,
});

export type PasswordChangeValues = z.infer<typeof passwordChangeSchema>;
