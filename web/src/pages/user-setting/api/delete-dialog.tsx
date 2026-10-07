import { Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useDeleteApiToken } from "@/hooks/use-api-token-request";
import { notifySuccess } from "@/services/notify";
import { isAlreadyGone, notifyDeleteFailure } from "./errors";
import { tokenTail } from "./mask";

/**
 * Delete confirmation for one row. The trigger is the row's own button, so Radix returns focus to it when the
 * dialog is dismissed; the id sent is this row's token. Cancel (Keep token) takes the initial focus and an overlay
 * click does not close the dialog. After a delete the page decides where focus goes (the table caption).
 */
export function DeleteTokenDialog({ token, onDeleted }: { token: string; onDeleted: () => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const remove = useDeleteApiToken();
  const removed = useRef(false);
  const tail = tokenTail(token);

  async function confirm(): Promise<void> {
    if (remove.isPending) return;
    try {
      await remove.mutateAsync(token);
      notifySuccess(t("tokens.deleted"));
      removed.current = true;
    } catch (error) {
      if (isAlreadyGone(error)) removed.current = true;
      else notifyDeleteFailure();
    }
    setOpen(false);
    if (removed.current) onDeleted();
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          data-testid="token-delete"
          aria-label={t("tokens.action.delete", { last4: tail })}
          className="hover:text-destructive focus-visible:text-destructive"
        >
          <Trash2 aria-hidden="true" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent
        data-testid="token-delete-dialog"
        onCloseAutoFocus={(event) => {
          if (removed.current) event.preventDefault();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>{t("tokens.delete.title")}</AlertDialogTitle>
          <AlertDialogDescription>{t("tokens.delete.body", { last4: tail })}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="token-delete-keep">{t("tokens.delete.keep")}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            data-testid="token-delete-confirm"
            aria-disabled={remove.isPending ? true : undefined}
            onClick={(event) => {
              event.preventDefault();
              void confirm();
            }}
          >
            {t("tokens.delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
