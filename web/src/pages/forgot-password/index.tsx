import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { CodeStep } from "./code-step";
import { EmailStep } from "./email-step";
import { PasswordStep } from "./password-step";
import type { StepMessage } from "./step-parts";

type Step = 1 | 2 | 3;

const TITLE_KEYS = { 1: "auth.forgot.step1.title", 2: "auth.forgot.step2.title", 3: "auth.forgot.step3.title" } as const;

/**
 * Forgot password (UI-SPEC, D-02, D-06, D-07, D-08): email, code, new password, three steps on one public route.
 *
 * Everything lives in component state. The email is kept so a return to step 1 is pre-filled; the code and the
 * new password are held by their step's form only, and the reset ticket is held here. None of it is written to
 * the URL, router state, storage or a query key, so a reload starts again at step 1 (T-02-85).
 */
export default function ForgotPasswordPage() {
  const { t, i18n } = useTranslation();
  const [step, setStep] = useState<Step>(1);
  const [email, setEmail] = useState("");
  const [ticket, setTicket] = useState("");
  const [notice, setNotice] = useState<StepMessage | null>(null);
  const noticeCount = useRef(0);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const firstRender = useRef(true);

  // First load focuses the email field; every later step change moves focus to the step title, which announces it.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      frameRef.current?.querySelector<HTMLInputElement>("input")?.focus();
    } else {
      titleRef.current?.focus();
    }
  }, [step]);

  useEffect(() => {
    document.title = t("auth.forgot.pageTitle");
  }, [t, i18n.language]);

  const backToStart = (message: string) => {
    noticeCount.current += 1;
    setNotice({ message, id: noticeCount.current });
    setTicket("");
    setStep(1);
  };

  return (
    <div data-testid="forgot-page" className="mx-auto flex w-full max-w-sm flex-col items-center gap-6 py-16 [@media(min-height:640px)]:py-0">
      <span className="text-xl font-semibold leading-tight">{t("app.wordmark")}</span>
      <Card className="w-full">
        <CardHeader>
          <p className="text-xs font-normal text-muted-foreground">{t("auth.forgot.step", { current: step })}</p>
          <h1 ref={titleRef} tabIndex={-1} data-testid="forgot-title" className="text-xl font-semibold leading-tight focus:outline-none">
            {t(TITLE_KEYS[step])}
          </h1>
        </CardHeader>
        <CardContent ref={frameRef}>
          {step === 1 ? (
            <EmailStep
              email={email}
              notice={notice}
              onSent={(sent) => {
                setEmail(sent);
                setNotice(null);
                setStep(2);
              }}
            />
          ) : null}
          {step === 2 ? (
            <CodeStep
              email={email}
              onVerified={(granted) => {
                setTicket(granted);
                setStep(3);
              }}
              onExhausted={backToStart}
            />
          ) : null}
          {step === 3 ? <PasswordStep email={email} ticket={ticket} onRefused={backToStart} /> : null}
        </CardContent>
      </Card>
    </div>
  );
}
