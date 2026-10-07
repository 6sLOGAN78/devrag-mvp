import { z } from "zod";
import { emailField, newPasswordField } from "@/pages/login/schemas";

/** Number of digits in the emailed code. */
export const CODE_LENGTH = 6;

/** Step 1: the account email, trimmed and lowercased on output. */
export const emailStepSchema = z.object({ email: emailField });

/** Step 2: exactly six digits, nothing else (letters, spaces and other lengths fail). Issues are i18n keys. */
export const codeStepSchema = z.object({
  code: z.string().regex(new RegExp(`^\\d{${CODE_LENGTH}}$`), "errors.code.invalid"),
});

/** Step 3: 8 to 128 characters through the shared rule; never trimmed. */
export const passwordStepSchema = z.object({ password: newPasswordField });

export type EmailStepValues = z.infer<typeof emailStepSchema>;
export type CodeStepValues = z.infer<typeof codeStepSchema>;
export type PasswordStepValues = z.infer<typeof passwordStepSchema>;
