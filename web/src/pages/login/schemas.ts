import { z } from "zod";

/** Server rules mirrored for instant feedback (D-02, D-29). The server stays the authority. */
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;
export const NICKNAME_MAX = 64;
const EMAIL_MAX = 255;

// One "@", a dot in the domain, no whitespace: the same shape the server accepts (internal/service/account.go).
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// Control and format characters (bidirectional overrides, zero-width) and angle brackets are refused by the server.
const NICKNAME_FORBIDDEN = /[\p{Cc}\p{Cf}<>]/u;

/** Characters, not UTF-16 units, matching the server's rune count. */
const length = (value: string): number => Array.from(value).length;

/** Trimmed, lowercased on output. Issues are i18n keys. */
export const emailField = z
  .string()
  .transform((value) => value.trim().toLowerCase())
  .superRefine((value, ctx) => {
    if (value === "") ctx.addIssue({ code: z.ZodIssueCode.custom, message: "errors.email.required" });
    else if (value.length > EMAIL_MAX || !EMAIL_SHAPE.test(value)) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "errors.email.invalid" });
  });

export const nicknameField = z
  .string()
  .transform((value) => value.trim())
  .superRefine((value, ctx) => {
    const size = length(value);
    if (size < 1) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "errors.nickname.required" });
    else if (size > NICKNAME_MAX) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "errors.nickname.max" });
    else if (NICKNAME_FORBIDDEN.test(value)) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "errors.nickname.invalid" });
  });

/** Length only, no composition rule, never trimmed. Reused by registration, password change and reset. */
export const newPasswordField = z.string().superRefine((value, ctx) => {
  const size = length(value);
  if (size < PASSWORD_MIN) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "errors.password.min" });
  else if (size > PASSWORD_MAX) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "errors.password.max" });
});

/** Sign in applies no length rule: an account created under an older rule must still be able to sign in. */
export const loginSchema = z.object({
  email: emailField,
  password: z.string().min(1, "errors.password.required"),
});

export const registerSchema = z.object({
  nickname: nicknameField,
  email: emailField,
  password: newPasswordField,
});

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
