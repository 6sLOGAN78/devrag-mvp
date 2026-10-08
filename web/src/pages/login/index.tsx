import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useSearchParams } from "react-router";
import { SessionSkeleton } from "@/components/session-skeleton";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useAuthorization } from "@/hooks/use-authorization";
import { useSystemConfigRequest } from "@/hooks/use-system-config-request";
import { useUserInfoRequest } from "@/hooks/use-user-info-request";
import { sanitiseNext } from "@/utils/safe-next";
import { getAuthorization } from "@/utils/authorization";
import { SignInForm } from "./sign-in-form";
import { SignUpForm } from "./sign-up-form";

type Mode = "login" | "register";

/** A visitor who already holds a token is sent on once the server confirms it; a rejected token falls through to the form. */
function ExistingSession({ next, onFailed }: { next: string | null; onFailed: () => void }) {
  const token = useAuthorization();
  const query = useUserInfoRequest();
  const failed = token === null || (query.isError && !query.isFetching);
  useEffect(() => {
    if (failed) onFailed();
  }, [failed, onFailed]);
  if (query.data) return <Navigate to={sanitiseNext(next)} replace />;
  return <SessionSkeleton />;
}

function AuthCard() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const config = useSystemConfigRequest();
  const next = params.get("next");
  const wantsRegister = params.get("mode") === "register";
  const mode: Mode = wantsRegister && config.registerEnabled ? "register" : "login";
  const [error, setError] = useState<{ message: string; id: number } | null>(null);
  const errorCount = useRef(0);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const userSwitched = useRef(false);
  // Set when registration succeeded but the automatic sign in did not: the sign-in form opens with this email.
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);

  // Initial focus lands on the first field; after a deliberate mode switch it lands on the card title.
  useEffect(() => {
    if (userSwitched.current) {
      userSwitched.current = false;
      titleRef.current?.focus();
    } else {
      formRef.current?.querySelector<HTMLInputElement>("input")?.focus();
    }
  }, [mode]);

  useEffect(() => {
    document.title = t(mode === "register" ? "auth.register.pageTitle" : "auth.login.pageTitle");
  }, [t, i18n.language, mode]);

  const showError = (message: string | null) => {
    errorCount.current += 1;
    setError(message === null ? null : { message, id: errorCount.current });
  };

  const onRegistered = (email: string) => {
    setError(null);
    setRegisteredEmail(email);
    const nextParams = new URLSearchParams(params);
    nextParams.delete("mode");
    setParams(nextParams);
  };

  const switchMode = (to: Mode) => {
    userSwitched.current = true;
    setError(null);
    setRegisteredEmail(null);
    const nextParams = new URLSearchParams(params);
    if (to === "register") nextParams.set("mode", "register");
    else nextParams.delete("mode");
    setParams(nextParams);
  };

  const registrationRefused = wantsRegister && !config.registerEnabled && !config.isLoading;

  return (
    <div data-testid="login-page" className="mx-auto flex w-full max-w-sm flex-col items-center gap-6 py-16 [@media(min-height:640px)]:py-0">
      <span className="text-xl font-semibold leading-tight">{t("app.wordmark")}</span>
      <Card className="w-full">
        <CardHeader>
          <h1 ref={titleRef} tabIndex={-1} className="text-xl font-semibold leading-tight focus:outline-none">
            {t(mode === "register" ? "auth.register.title" : "auth.login.title")}
          </h1>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {error ? (
            <Alert key={error.id} data-testid="login-error">
              {error.message}
            </Alert>
          ) : null}
          {registeredEmail !== null && mode === "login" ? (
            <p data-testid="login-notice" role="status" className="rounded-md border bg-card px-3 py-2 text-sm font-normal text-card-foreground">
              {t("auth.register.createdSignIn")}
            </p>
          ) : null}
          <div ref={formRef}>
            {mode === "register" ? (
              <SignUpForm next={next} onError={showError} onRegistered={onRegistered} />
            ) : (
              <SignInForm next={next} onError={showError} defaultEmail={registeredEmail ?? ""} />
            )}
          </div>
          {mode === "login" && config.registerEnabled ? (
            <p className="text-center text-sm font-normal text-muted-foreground">
              {t("auth.login.noAccount")}{" "}
              <Button type="button" variant="link" data-testid="mode-switch" className="h-auto p-0" onClick={() => switchMode("register")}>
                {t("auth.login.createOne")}
              </Button>
            </p>
          ) : null}
          {mode === "register" ? (
            <p className="text-center text-sm font-normal text-muted-foreground">
              {t("auth.register.haveAccount")}{" "}
              <Button type="button" variant="link" data-testid="mode-switch" className="h-auto p-0" onClick={() => switchMode("login")}>
                {t("auth.register.signIn")}
              </Button>
            </p>
          ) : null}
          {registrationRefused ? <p className="text-center text-xs font-normal text-muted-foreground">{t("auth.login.registrationOff")}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  const [next] = useSearchParams();
  const [checking, setChecking] = useState(() => getAuthorization() !== null);
  if (checking) return <ExistingSession next={next.get("next")} onFailed={() => setChecking(false)} />;
  return <AuthCard />;
}
