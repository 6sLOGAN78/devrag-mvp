import { zodResolver } from "@hookform/resolvers/zod";
import { CircleAlert, Loader2 } from "lucide-react";
import { useId, useRef, useState, type ChangeEvent } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { AvatarInitials } from "@/components/avatar-initials";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useProfileRequest, type ProfileEdit } from "@/hooks/use-profile-request";
import type { SessionUser } from "@/interfaces/user";
import { notifySuccess } from "@/services/notify";
import { nicknameField } from "@/pages/login/schemas";
import { AvatarError, downscaleToDataUrl, type AvatarErrorKey } from "./avatar";
import { profileErrorMessage } from "./profile-error";

const profileSchema = z.object({ nickname: nicknameField });
type ProfileValues = z.infer<typeof profileSchema>;

/** Nickname and avatar. The avatar is staged (previewed, not sent) and saved together with the form. */
export function ProfileCard({ user }: { user: SessionUser }) {
  const { t } = useTranslation();
  const save = useProfileRequest();
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    mode: "onChange",
    defaultValues: { nickname: user.nickname },
  });
  // undefined = unchanged, "" = removed, otherwise the data URL the avatar helper produced.
  const [staged, setStaged] = useState<string | undefined>(undefined);
  const [avatarError, setAvatarError] = useState<AvatarErrorKey | null>(null);
  const [formError, setFormError] = useState<{ message: string; id: number } | null>(null);
  const inFlight = useRef(false);
  const picks = useRef(0);
  const errorCount = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const ids = { email: useId(), emailHelp: useId(), avatarHelp: useId(), avatarError: useId() };

  const parsed = nicknameField.safeParse(form.watch("nickname"));
  const nicknameChanged = parsed.success && parsed.data !== user.nickname;
  const avatarChanged = staged !== undefined && staged !== user.avatar;
  const busy = save.isPending;
  const canSave = parsed.success && (nicknameChanged || avatarChanged) && !busy;
  const shownAvatar = staged ?? user.avatar;

  const choose = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const pick = (picks.current += 1);
    setAvatarError(null);
    try {
      const dataUrl = await downscaleToDataUrl(file);
      if (pick === picks.current) setStaged(dataUrl);
    } catch (error) {
      if (pick === picks.current) setAvatarError(error instanceof AvatarError ? error.key : "errors.avatar.decode");
    }
  };

  const onSubmit = form.handleSubmit(async (values) => {
    if (inFlight.current || !canSave) return;
    inFlight.current = true;
    setFormError(null);
    const edit: ProfileEdit = {
      ...(nicknameChanged ? { nickname: values.nickname } : {}),
      ...(avatarChanged ? { avatar: staged } : {}),
    };
    try {
      await save.mutateAsync(edit);
      notifySuccess(t("profile.saved"));
      form.reset({ nickname: values.nickname });
      setStaged(undefined);
    } catch (error) {
      errorCount.current += 1;
      setFormError({ message: profileErrorMessage(error, t), id: errorCount.current });
    } finally {
      inFlight.current = false;
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("profile.card.title")}</CardTitle>
      </CardHeader>
      <Form {...form}>
        <form data-testid="profile-form" noValidate aria-busy={busy || undefined} onSubmit={onSubmit}>
          <CardContent className="flex max-w-md flex-col gap-4">
            {formError ? (
              <Alert key={formError.id} data-testid="alert-form-error">
                {formError.message}
              </Alert>
            ) : null}
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-3">
                <AvatarInitials avatar={shownAvatar} nickname={user.nickname} email={user.email} size="lg" />
                {/* The native picker is hidden; the button is the keyboard path to it. */}
                <input
                  ref={fileInput}
                  data-testid="avatar-input"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  aria-label={t("profile.avatar.change")}
                  tabIndex={-1}
                  className="sr-only"
                  onChange={(event) => void choose(event)}
                />
                <Button
                  type="button"
                  variant="outline"
                  aria-describedby={avatarError ? ids.avatarError : ids.avatarHelp}
                  onClick={() => fileInput.current?.click()}
                >
                  {t("profile.avatar.change")}
                </Button>
                {shownAvatar !== "" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    data-testid="avatar-remove"
                    onClick={() => {
                      picks.current += 1;
                      setAvatarError(null);
                      setStaged("");
                    }}
                  >
                    {t("profile.avatar.remove")}
                  </Button>
                ) : null}
              </div>
              <p id={ids.avatarHelp} className="text-xs font-normal text-muted-foreground">
                {t("profile.avatar.help")}
              </p>
              {avatarError ? (
                <p id={ids.avatarError} role="alert" className="flex items-start gap-1 text-xs font-normal text-destructive">
                  <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
                  <span>{t(avatarError)}</span>
                </p>
              ) : null}
            </div>
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
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.email}>{t("auth.field.email")}</Label>
              <Input
                id={ids.email}
                data-testid="field-email"
                type="text"
                value={user.email}
                readOnly
                aria-readonly="true"
                aria-describedby={ids.emailHelp}
              />
              <p id={ids.emailHelp} className="text-xs font-normal text-muted-foreground">
                {t("profile.email.help")}
              </p>
            </div>
          </CardContent>
          <CardFooter>
            <Button
              type="submit"
              data-testid="profile-submit"
              aria-disabled={canSave ? undefined : true}
              aria-busy={busy || undefined}
              onClick={(event) => {
                if (!canSave) event.preventDefault();
              }}
            >
              {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
              {t("profile.save")}
            </Button>
            <p role="status" className="sr-only">
              {busy ? t("profile.saving") : ""}
            </p>
          </CardFooter>
        </form>
      </Form>
    </Card>
  );
}
