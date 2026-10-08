import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { PasswordInput } from "@/components/password-input";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { SignInAfterSignUpError, useAuthRequest } from "@/hooks/use-auth-request";
import { sanitiseNext } from "@/utils/safe-next";
import { authErrorMessage } from "./auth-error";
import { registerSchema, type RegisterValues } from "./schemas";

interface SignUpFormProps {
  next: string | null;
  onError: (message: string | null) => void;
  /** The account exists but signing in failed: the page moves to the sign-in form with this email. */
  onRegistered: (email: string) => void;
}

export function SignUpForm({ next, onError, onRegistered }: SignUpFormProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const auth = useAuthRequest();
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    mode: "onTouched",
    reValidateMode: "onChange",
    defaultValues: { nickname: "", email: "", password: "" },
  });
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [resetSignal, setResetSignal] = useState(0);

  const onSubmit = async (values: RegisterValues) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    onError(null);
    try {
      await auth.signUp(values);
      void navigate(sanitiseNext(next), { replace: true });
    } catch (error) {
      if (error instanceof SignInAfterSignUpError) {
        onRegistered(values.email);
        return;
      }
      // Every field is kept so the person can correct one thing (duplicate email, a refused nickname).
      onError(authErrorMessage(error, "register", t));
      setResetSignal((value) => value + 1);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <Form {...form}>
      <form data-testid="register-form" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <FormField
          control={form.control}
          name="nickname"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("auth.field.nickname")}</FormLabel>
              <FormControl>
                <Input {...field} data-testid="field-nickname" type="text" autoComplete="nickname" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("auth.field.email")}</FormLabel>
              <FormControl>
                <Input {...field} data-testid="field-email" type="email" autoComplete="email" inputMode="email" placeholder={t("auth.field.emailPlaceholder")} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("auth.field.password")}</FormLabel>
              <FormControl>
                <PasswordInput {...field} data-testid="field-password" autoComplete="new-password" resetSignal={resetSignal} />
              </FormControl>
              <FormDescription>{t("auth.field.passwordHelp")}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button
          type="submit"
          data-testid="register-submit"
          className="mt-2 w-full"
          aria-disabled={busy || undefined}
          aria-busy={busy || undefined}
          onClick={(event) => {
            if (busy) event.preventDefault();
          }}
        >
          {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
          {t("auth.register.submit")}
        </Button>
        <p role="status" className="sr-only">
          {busy ? t("auth.register.pending") : ""}
        </p>
      </form>
    </Form>
  );
}
