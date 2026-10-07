import { zodResolver } from "@hookform/resolvers/zod";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useCountdown } from "@/hooks/use-countdown";
import { usePasswordResetRequest } from "@/hooks/use-password-reset-request";
import { ApiError } from "@/services/http";
import { clampRetryAfter, isRefusal, resetErrorMessage, serverMessage } from "./reset-error";
import { CODE_LENGTH, codeStepSchema, type CodeStepValues } from "./schemas";
import { BackToSignIn, StepAlert, SubmitButton, type StepMessage } from "./step-parts";

/** The server destroys a code after this many wrong attempts, so the page returns to step 1 after the same number. */
export const MAX_WRONG_ATTEMPTS = 5;
/** One send per minute per email (D-06): the resend control mirrors it. */
export const RESEND_SECONDS = 60;

interface CodeStepProps {
  email: string;
  /** The code was accepted; `ticket` is the single-use reset ticket. */
  onVerified: (ticket: string) => void;
  /** Five wrong codes: back to step 1 with the server's message. */
  onExhausted: (message: string) => void;
}

const digitsOnly = (value: string) => value.replace(/\D/g, "").slice(0, CODE_LENGTH);

export function CodeStep({ email, onVerified, onExhausted }: CodeStepProps) {
  const { t } = useTranslation();
  const reset = usePasswordResetRequest();
  const countdown = useCountdown(RESEND_SECONDS);
  const form = useForm<CodeStepValues>({ resolver: zodResolver(codeStepSchema), mode: "onTouched", reValidateMode: "onChange", defaultValues: { code: "" } });
  const inFlight = useRef(false);
  const resendInFlight = useRef(false);
  const wrongAttempts = useRef(0);
  const count = useRef(0);
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState<StepMessage | null>(null);
  const [resent, setResent] = useState(false);

  const show = (message: string) => {
    count.current += 1;
    setError({ message, id: count.current });
  };

  const onSubmit = async (values: CodeStepValues) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setResent(false);
    try {
      const { ticket } = await reset.verifyCode(email, values.code);
      onVerified(ticket);
    } catch (failure) {
      if (isRefusal(failure)) {
        wrongAttempts.current += 1;
        const message = serverMessage(failure, t("auth.forgot.codeFallback"));
        if (wrongAttempts.current >= MAX_WRONG_ATTEMPTS) {
          onExhausted(message);
          return;
        }
        show(message);
      } else {
        show(resetErrorMessage(failure, t, t("auth.forgot.codeFallback")));
      }
      // The typed code stays so a typo can be corrected; it is selected so retyping replaces it.
      form.setFocus("code", { shouldSelect: true });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const resend = async () => {
    if (resendInFlight.current || countdown.remaining > 0) return;
    resendInFlight.current = true;
    setResending(true);
    setError(null);
    setResent(false);
    try {
      await reset.requestCode(email);
      wrongAttempts.current = 0;
      form.reset({ code: "" });
      countdown.start(RESEND_SECONDS);
      setResent(true);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 429) {
        countdown.start(clampRetryAfter(failure.retryAfter ?? RESEND_SECONDS));
      }
      show(resetErrorMessage(failure, t, t("auth.error.fallback")));
    } finally {
      resendInFlight.current = false;
      setResending(false);
    }
  };

  return (
    <Form {...form}>
      <form data-testid="forgot-step-2" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <p className="text-sm font-normal text-muted-foreground">{t("auth.forgot.step2.body", { email })}</p>
        <StepAlert error={error} />
        <p role="status" className="text-sm font-normal text-muted-foreground empty:hidden">
          {resent ? t("auth.forgot.resent") : ""}
        </p>
        <FormField
          control={form.control}
          name="code"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("auth.forgot.code")}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  data-testid="field-code"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  autoComplete="one-time-code"
                  maxLength={CODE_LENGTH}
                  placeholder={t("auth.forgot.codePlaceholder")}
                  className="font-mono tracking-[0.3em]"
                  onChange={(event) => field.onChange(digitsOnly(event.target.value))}
                  onPaste={(event) => {
                    event.preventDefault();
                    field.onChange(digitsOnly(event.clipboardData.getData("text")));
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <SubmitButton busy={busy} label={t("auth.forgot.step2.submit")} pendingLabel={t("auth.forgot.pending")} />
        <Button
          type="button"
          variant="link"
          data-testid="forgot-resend"
          className="h-auto self-center p-0 text-sm font-normal"
          disabled={countdown.remaining > 0 || resending}
          onClick={() => void resend()}
        >
          {countdown.remaining > 0 ? t("auth.forgot.resendIn", { seconds: countdown.remaining }) : t("auth.forgot.resend")}
        </Button>
        <BackToSignIn />
      </form>
    </Form>
  );
}
