import { Loader2 } from "lucide-react";
import { useEffect, useRef, type MutableRefObject, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { ProviderFailure } from "./errors";

/** Pieces the set up, change and add model dialogs share. */

interface DialogShellProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Where focus goes when the dialog has closed; the page decides (the row, or the Providers title). */
  onCloseAutoFocus: (event: Event) => void;
  /** True while the provider is being called: an overlay click must not dismiss the dialog then. Esc and Close still do. */
  pendingRef: MutableRefObject<boolean>;
  title: string;
  children: ReactNode;
}

/** The modal frame. The form inside is mounted only while the dialog is open, so closing discards every typed value. */
export function DialogShell({ open, onOpenChange, onCloseAutoFocus, pendingRef, title, children }: DialogShellProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="provider-dialog"
        aria-describedby={undefined}
        onCloseAutoFocus={onCloseAutoFocus}
        onInteractOutside={(event) => {
          if (pendingRef.current) event.preventDefault();
        }}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}

/**
 * The inline answer to a failed call. A provider refusal has a title that names the provider and, under it, the
 * provider's own reason; every other answer is one fixed sentence. Server text renders as a text node. The alert takes
 * focus when it appears, so the answer is read and the keyboard is next to the form.
 */
export function FailureAlert({ failure, provider, workspace }: { failure: ProviderFailure; provider: string; workspace: string }) {
  const { t } = useTranslation();
  const alert = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    alert.current?.focus();
  }, [failure]);
  return (
    <Alert
      ref={alert}
      tabIndex={-1}
      data-testid={failure.refusal ? "provider-refusal" : "provider-error"}
      className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {failure.refusal ? <p className="font-semibold">{t("models.refused.title", { provider })}</p> : null}
      <p>{failure.text ?? t(failure.key, { provider, workspace })}</p>
    </Alert>
  );
}

/** The live line under the fields while the provider is being called. The number matches the 45 s client timeout (two 20 s server tests). */
export function PendingStatus() {
  const { t } = useTranslation();
  return (
    <p role="status" data-testid="provider-test-status" className="text-sm font-normal text-muted-foreground">
      {t("models.testing")}
    </p>
  );
}

/** Close and "Test and save". The submit button stays focusable while busy (`aria-disabled`), so focus is not lost. */
export function SubmitFooter({ busy }: { busy: boolean }) {
  const { t } = useTranslation();
  return (
    <DialogFooter>
      <DialogClose asChild>
        <Button type="button" variant="ghost">
          {t("dialog.close")}
        </Button>
      </DialogClose>
      <Button
        type="submit"
        data-testid="provider-submit"
        aria-busy={busy || undefined}
        aria-disabled={busy || undefined}
        className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
      >
        {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
        {t("models.submit")}
      </Button>
    </DialogFooter>
  );
}
