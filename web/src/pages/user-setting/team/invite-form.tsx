import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useInviteMember } from "@/hooks/use-team-request";
import { emailField } from "@/pages/login/schemas";
import { notifySuccess } from "@/services/notify";
import { inviteErrorMessage } from "./errors";

const inviteSchema = z.object({ email: emailField });
type InviteValues = z.infer<typeof inviteSchema>;

/**
 * Owner-only invite form (D-13). The email is validated with the shared schema; the server's answer for an unknown
 * email, an existing member, a pending invitation or yourself is shown as returned, with no hint added here.
 * A request in flight blocks a second submit; success clears and refocuses the field.
 */
export function InviteForm({ tenantId }: { tenantId: string }) {
  const { t } = useTranslation();
  const invite = useInviteMember(tenantId);
  const form = useForm<InviteValues>({
    resolver: zodResolver(inviteSchema),
    mode: "onSubmit",
    reValidateMode: "onChange",
    defaultValues: { email: "" },
  });
  const input = useRef<HTMLInputElement | null>(null);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(values: InviteValues): Promise<void> {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await invite.mutateAsync(values.email);
      notifySuccess(t("team.invite.sentTitle"), t("team.invite.sentBody", { email: values.email }));
      form.reset({ email: "" });
      input.current?.focus();
    } catch (failure) {
      setError(inviteErrorMessage(failure, t));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <Form {...form}>
      <form data-testid="invite-form" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-3">
        {error === null ? null : <Alert data-testid="alert-form-error">{error}</Alert>}
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("team.invite.email")}</FormLabel>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                <div className="min-w-0 flex-1">
                  <FormControl>
                    <Input
                      {...field}
                      data-testid="invite-email"
                      ref={(element) => {
                        field.ref(element);
                        input.current = element;
                      }}
                      type="email"
                      autoComplete="off"
                      inputMode="email"
                      onChange={(event) => {
                        setError(null);
                        field.onChange(event);
                      }}
                    />
                  </FormControl>
                </div>
                <Button
                  type="submit"
                  data-testid="invite-submit"
                  aria-busy={busy || undefined}
                  aria-disabled={busy || undefined}
                  className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
                >
                  {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
                  {t("team.invite.submit")}
                </Button>
              </div>
              <FormDescription>{t("team.invite.help")}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </form>
    </Form>
  );
}
