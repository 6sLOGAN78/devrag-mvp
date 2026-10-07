import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/** A message shown above a step's fields. `id` changes per message so a repeat is announced again. */
export interface StepMessage {
  message: string;
  id: number;
}

export function StepAlert({ error }: { error: StepMessage | null }) {
  return error ? (
    <Alert key={error.id} data-testid="forgot-error">
      {error.message}
    </Alert>
  ) : null;
}

/** Primary button that stays in the tab order while pending but does nothing (the same pattern as sign in). */
export function SubmitButton({ busy, label, pendingLabel }: { busy: boolean; label: string; pendingLabel: string }) {
  return (
    <>
      <Button
        type="submit"
        data-testid="forgot-submit"
        className="mt-2 w-full"
        aria-disabled={busy || undefined}
        aria-busy={busy || undefined}
        onClick={(event) => {
          if (busy) event.preventDefault();
        }}
      >
        {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
        {label}
      </Button>
      <p role="status" className="sr-only">
        {busy ? pendingLabel : ""}
      </p>
    </>
  );
}

export function BackToSignIn() {
  const { t } = useTranslation();
  return (
    <Button asChild variant="link" className="h-auto self-center p-0 text-sm font-normal">
      <Link to="/login" data-testid="forgot-back">
        {t("auth.forgot.back")}
      </Link>
    </Button>
  );
}
