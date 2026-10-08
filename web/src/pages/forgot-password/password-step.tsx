import { zodResolver } from "@hookform/resolvers/zod";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { PasswordInput } from "@/components/password-input";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { usePasswordResetRequest } from "@/hooks/use-password-reset-request";
import { notifySuccess } from "@/services/notify";
import { isPasswordRejection, isRefusal, resetErrorMessage, serverMessage } from "./reset-error";
import { passwordStepSchema, type PasswordStepValues } from "./schemas";
import { BackToSignIn, StepAlert, SubmitButton, type StepMessage } from "./step-parts";

interface PasswordStepProps {
  email: string;
  /** Single-use reset ticket from step 2. Held in memory only. */
  ticket: string;
  /** The server refused the ticket (used, expired, foreign): back to step 1 with its message. */
  onRefused: (message: string) => void;
}

/**
 * Step 3 (D-02, D-08). One password field with the show/hide toggle, no confirmation. On success the page goes to
 * /login with a toast; the reset created no session and any local one has been dropped.
 */
export function PasswordStep({ email, ticket, onRefused }: PasswordStepProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const reset = usePasswordResetRequest();
  const form = useForm<PasswordStepValues>({ resolver: zodResolver(passwordStepSchema), mode: "onTouched", reValidateMode: "onChange", defaultValues: { password: "" } });
  const inFlight = useRef(false);
  const count = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<StepMessage | null>(null);

  const onSubmit = async (values: PasswordStepValues) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await reset.resetPassword(email, ticket, values.password);
      notifySuccess(t("auth.forgot.doneTitle"), t("auth.forgot.doneBody"));
      await navigate("/login", { replace: true });
    } catch (failure) {
      if (isRefusal(failure) && !isPasswordRejection(failure)) {
        onRefused(serverMessage(failure, t("auth.forgot.sessionFallback")));
        return;
      }
      count.current += 1;
      setError({ message: resetErrorMessage(failure, t, t("auth.forgot.sessionFallback")), id: count.current });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <Form {...form}>
      <form data-testid="forgot-step-3" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <p className="text-sm font-normal text-muted-foreground">{t("auth.forgot.step3.body")}</p>
        <StepAlert error={error} />
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("auth.forgot.step3.field")}</FormLabel>
              <FormControl>
                <PasswordInput {...field} data-testid="field-password" autoComplete="new-password" />
              </FormControl>
              <FormDescription>{t("auth.field.passwordHelp")}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <SubmitButton busy={busy} label={t("auth.forgot.step3.submit")} pendingLabel={t("auth.forgot.pending")} />
        <BackToSignIn />
      </form>
    </Form>
  );
}
