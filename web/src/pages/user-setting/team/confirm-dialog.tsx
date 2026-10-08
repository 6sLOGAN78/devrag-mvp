import type { MutableRefObject } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  keepLabel: string;
  confirmLabel: string;
  /** Destructive fill for remove, withdraw and leave; the role change confirm is a plain primary. */
  destructive?: boolean;
  pending: boolean;
  onConfirm: () => void;
  /** The control that opened the dialog; it gets focus back on dismissal (the dialog has no Radix trigger of its own). */
  opener: MutableRefObject<HTMLElement | null>;
  /** True when the row behind the opener is gone, so the owner of the dialog places focus itself (the table caption). */
  keepFocusElsewhere: () => boolean;
}

/**
 * The one confirmation shape of the Team page (UI-SPEC "Interaction conventions"): Radix focuses the keep button
 * first, an overlay click does not close it, and it cannot be dismissed while a request is running. The dialog has
 * no trigger of its own; the control that opened it is where focus returns when it is dismissed.
 */
export function ConfirmDialog({ open, onOpenChange, title, description, keepLabel, confirmLabel, destructive = false, pending, onConfirm, opener, keepFocusElsewhere }: ConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={(next) => (pending && !next ? undefined : onOpenChange(next))}>
      <AlertDialogContent
        data-testid="confirm-dialog"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          if (!keepFocusElsewhere()) opener.current?.focus();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="confirm-keep" aria-disabled={pending ? true : undefined}>
            {keepLabel}
          </AlertDialogCancel>
          <AlertDialogAction
            variant={destructive ? "destructive" : "default"}
            data-testid="confirm-action"
            aria-busy={pending ? true : undefined}
            aria-disabled={pending ? true : undefined}
            onClick={(event) => {
              event.preventDefault();
              if (!pending) onConfirm();
            }}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
