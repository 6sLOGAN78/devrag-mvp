import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { PasswordInput } from "@/components/password-input";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useAuthRequest } from "@/hooks/use-auth-request";
import { sanitiseNext } from "@/utils/safe-next";
import { authErrorMessage } from "./auth-error";
import { loginSchema, type LoginValues } from "./schemas";

interface SignInFormProps {
  next: string | null;
  onError: (message: string | null) => void;
  /** Prefilled after a registration whose automatic sign-in failed. */
  defaultEmail?: string;
}

export function SignInForm({ next, onError, defaultEmail = "" }: SignInFormProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const auth = useAuthRequest();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    mode: "onTouched",
    reValidateMode: "onChange",
    defaultValues: { email: defaultEmail, password: "" },
  });
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [resetSignal, setResetSignal] = useState(0);

  const onSubmit = async (values: LoginValues) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    onError(null);
    try {
      await auth.signIn(values.email, values.password);
      void navigate(sanitiseNext(next), { replace: true });
    } catch (error) {
      onError(authErrorMessage(error, "login", t));
      // The email stays; the password is gone from the field, hidden again, and focus is ready for the retry.
      form.setValue("password", "");
      setResetSignal((value) => value + 1);
      form.setFocus("password");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <Form {...form}>
      <form data-testid="login-form" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
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
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <div className="flex items-baseline justify-between gap-2">
                <FormLabel>{t("auth.field.password")}</FormLabel>
                <Link to="/forgot-password" className="text-xs font-normal text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  {t("auth.login.forgot")}
                </Link>
              </div>
              <FormControl>
                <PasswordInput {...field} data-testid="field-password" autoComplete="current-password" resetSignal={resetSignal} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button
          type="submit"
          data-testid="login-submit"
          className="mt-2 w-full"
          aria-disabled={busy || undefined}
          aria-busy={busy || undefined}
          onClick={(event) => {
            if (busy) event.preventDefault();
          }}
        >
          {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
          {t("auth.login.submit")}
        </Button>
        <p role="status" className="sr-only">
          {busy ? t("auth.login.pending") : ""}
        </p>
      </form>
    </Form>
  );
}
