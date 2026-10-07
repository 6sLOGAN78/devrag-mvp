import { zodResolver } from "@hookform/resolvers/zod";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { usePasswordResetRequest } from "@/hooks/use-password-reset-request";
import { resetErrorMessage } from "./reset-error";
import { emailStepSchema, type EmailStepValues } from "./schemas";
import { BackToSignIn, StepAlert, SubmitButton, type StepMessage } from "./step-parts";

interface EmailStepProps {
  /** The email kept from an earlier pass, if any. */
  email: string;
  /** A message carried back from a later step (code exhausted, ticket refused). */
  notice: StepMessage | null;
  /** Called after any 2xx. The response is never inspected: every well-formed email looks the same (D-07). */
  onSent: (email: string) => void;
}

export function EmailStep({ email, notice, onSent }: EmailStepProps) {
  const { t } = useTranslation();
  const reset = usePasswordResetRequest();
  const form = useForm<EmailStepValues>({
    resolver: zodResolver(emailStepSchema),
    mode: "onTouched",
    reValidateMode: "onChange",
    defaultValues: { email },
  });
  const inFlight = useRef(false);
  const count = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<StepMessage | null>(notice);

  const onSubmit = async (values: EmailStepValues) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await reset.requestCode(values.email);
      onSent(values.email);
    } catch (failure) {
      count.current += 1;
      setError({ message: resetErrorMessage(failure, t, t("auth.error.fallback")), id: count.current });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <Form {...form}>
      <form data-testid="forgot-step-1" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <p className="text-sm font-normal text-muted-foreground">{t("auth.forgot.step1.body")}</p>
        <StepAlert error={error} />
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("auth.field.email")}</FormLabel>
              <FormControl>
                <Input {...field} data-testid="field-email" type="email" autoComplete="username" inputMode="email" placeholder={t("auth.field.emailPlaceholder")} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <SubmitButton busy={busy} label={t("auth.forgot.step1.submit")} pendingLabel={t("auth.forgot.pending")} />
        <BackToSignIn />
      </form>
    </Form>
  );
}
