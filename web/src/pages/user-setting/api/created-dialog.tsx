import { Copy } from "lucide-react";
import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { copyToken } from "./clipboard";

/**
 * Shows a freshly created token in full (the one place besides a revealed row where the whole value is in the DOM).
 * The page passes `token` only while the dialog is open and clears it on close. No "shown once" wording: D-12 keeps
 * tokens listable. Focus goes back to the Create button, whichever one is on screen.
 */
export function CreatedTokenDialog({
  token,
  onClose,
  returnFocusTo,
}: {
  token: string | null;
  onClose: () => void;
  returnFocusTo: RefObject<HTMLButtonElement>;
}) {
  const { t } = useTranslation();
  return (
    <Dialog open={token !== null} onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent
        data-testid="token-created-dialog"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          returnFocusTo.current?.focus();
        }}
      >
        <DialogHeader>
          <DialogTitle>{t("tokens.created.title")}</DialogTitle>
          <DialogDescription>{t("tokens.created.body")}</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <input
            readOnly
            value={token ?? ""}
            aria-label={t("tokens.created.field")}
            data-testid="token-created-field"
            autoComplete="off"
            spellCheck={false}
            onFocus={(event) => event.currentTarget.select()}
            className="h-10 min-w-0 flex-1 rounded-md border border-input bg-background px-3 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          />
          <Button
            type="button"
            variant="outline"
            data-testid="token-created-copy"
            onClick={() => {
              if (token !== null) void copyToken(token);
            }}
          >
            <Copy aria-hidden="true" />
            {t("tokens.created.copy")}
          </Button>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" data-testid="token-created-done">
              {t("tokens.created.done")}
            </Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
