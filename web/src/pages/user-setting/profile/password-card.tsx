import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { PasswordInput } from "@/components/password-input";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { usePasswordChange } from "@/hooks/use-profile-request";
import { ApiError } from "@/services/http";
import { passwordChangeSchema, type PasswordChangeValues } from "./password-schema";
import { profileErrorMessage } from "./profile-error";

const EMPTY: PasswordChangeValues = { current: "", replacement: "", again: "" };

/**
 * Password card (D-02, D-08). The three values live only in the form and in the one request body: no mutation
 * object, query key, storage or log ever holds them. A wrong current password (HTTP 400) is shown inline and keeps
 * the session; success signs this device out locally (the server has already signed every device out) and goes to /login.
 */
export function PasswordCard() {
  const { t } = useTranslation();
  const changePassword = usePasswordChange();
  const form = useForm<PasswordChangeValues>({
    resolver: zodResolver(passwordChangeSchema),
    mode: "onTouched",
    reValidateMode: "onChange",
    defaultValues: EMPTY,
  });
  const inFlight = useRef(false);
  const errorCount = useRef(0);
  const alertId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; id: number; rejected: boolean } | null>(null);
  const [resetSignal, setResetSignal] = useState(0);
  const [focusSignal, setFocusSignal] = useState(0);

  // After a refused attempt the current value is cleared and focused for the retry.
  useEffect(() => {
    if (focusSignal > 0) form.setFocus("current");
  }, [focusSignal, form]);

  const onSubmit = form.handleSubmit(async (values) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await changePassword(values.current, values.replacement);
      form.reset(EMPTY);
    } catch (failure) {
      errorCount.current += 1;
      setError({ message: profileErrorMessage(failure, t), id: errorCount.current, rejected: failure instanceof ApiError && failure.status === 400 });
      form.setValue("current", "");
      setResetSignal((value) => value + 1);
      setFocusSignal((value) => value + 1);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  });

  // The rejected marker is only passed while it applies, so the form's own validation attributes are not overridden otherwise.
  const rejected = error?.rejected ? { "aria-invalid": true as const, "aria-describedby": alertId } : {};

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("profile.password.title")}</CardTitle>
      </CardHeader>
      <Form {...form}>
        <form data-testid="password-form" noValidate aria-busy={busy || undefined} onSubmit={onSubmit}>
          <CardContent className="flex max-w-md flex-col gap-4">
            {error ? (
              <Alert key={error.id} id={alertId} data-testid="alert-password-error">
                {error.message}
              </Alert>
            ) : null}
            <FormField
              control={form.control}
              name="current"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("profile.password.current")}</FormLabel>
                  <FormControl>
                    <PasswordInput
                      {...field}
                      {...rejected}
                      data-testid="field-current-password"
                      autoComplete="current-password"
                      resetSignal={resetSignal}
                      onChange={(event) => {
                        if (error?.rejected) setError(null);
                        field.onChange(event);
                      }}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="replacement"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("profile.password.new")}</FormLabel>
                  <FormControl>
                    <PasswordInput {...field} data-testid="field-new-password" autoComplete="new-password" resetSignal={resetSignal} />
                  </FormControl>
                  <FormDescription>{t("auth.field.passwordHelp")}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="again"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("profile.password.confirm")}</FormLabel>
                  <FormControl>
                    <PasswordInput {...field} data-testid="field-confirm-password" autoComplete="new-password" resetSignal={resetSignal} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <p className="text-sm font-normal text-muted-foreground">{t("profile.password.note")}</p>
          </CardContent>
          <CardFooter>
            <Button
              type="submit"
              data-testid="password-submit"
              aria-disabled={busy || undefined}
              aria-busy={busy || undefined}
              onClick={(event) => {
                if (busy) event.preventDefault();
              }}
            >
              {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
              {t("profile.password.submit")}
            </Button>
            <p role="status" className="sr-only">
              {busy ? t("profile.password.pending") : ""}
            </p>
          </CardFooter>
        </form>
      </Form>
    </Card>
  );
}
