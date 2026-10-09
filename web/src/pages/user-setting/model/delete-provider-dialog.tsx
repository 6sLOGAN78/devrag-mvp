import { useState } from "react";
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
} from "@/components/ui/alert-dialog";
import { Alert } from "@/components/ui/alert";
import { clearMutation, useDeleteProviderRequest, useModelTenantId } from "@/hooks/use-llm-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { ApiError } from "@/services/http";
import { notifySuccess } from "@/services/notify";
import { deleteFailureKey } from "./errors";
import { providerName, type ProviderSpec } from "./providers";

interface DeleteProviderDialogProps {
  spec: ProviderSpec;
  /** Number of models the provider has in this workspace; worded in the body. */
  modelCount: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called once the credentials are gone, before the dialog closes. */
  onDeleted: () => void;
  onCloseAutoFocus: (event: Event) => void;
}

/**
 * Delete a provider's credentials (UI-37, checker flag 4). "Keep provider" has the initial focus, an overlay click
 * does not close the dialog, and a refusal is worded inside the dialog: nothing was removed, the dialog stays open.
 */
export function DeleteProviderDialog({ spec, modelCount, open, onOpenChange, onDeleted, onCloseAutoFocus }: DeleteProviderDialogProps) {
  const { t } = useTranslation();
  const tenantId = useModelTenantId();
  const workspace = useActiveWorkspace()?.name ?? "";
  const remove = useDeleteProviderRequest();
  const [failure, setFailure] = useState<string | null>(null);
  const name = providerName(spec, t);

  async function confirm(): Promise<void> {
    if (remove.isPending || tenantId === null) return;
    setFailure(null);
    try {
      await remove.mutateAsync({ tenantId, provider: spec.slug });
      notifySuccess(t("models.deleted", { provider: name }));
    } catch (error) {
      // 404: someone else already removed it. The list refreshes and the dialog closes quietly.
      if (!(error instanceof ApiError && error.status === 404)) {
        setFailure(deleteFailureKey(error));
        return;
      }
    } finally {
      clearMutation(remove);
    }
    onDeleted();
    onOpenChange(false);
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setFailure(null);
        onOpenChange(next);
      }}
    >
      <AlertDialogContent data-testid="provider-delete-dialog" onCloseAutoFocus={onCloseAutoFocus}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("models.delete.title", { provider: name })}</AlertDialogTitle>
          <AlertDialogDescription>{t("models.delete.body", { count: modelCount, provider: name, workspace })}</AlertDialogDescription>
        </AlertDialogHeader>
        {failure === null ? null : (
          <Alert data-testid="provider-delete-error">{t(failure, { workspace })}</Alert>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="provider-delete-keep">{t("models.delete.keep")}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            data-testid="provider-delete-confirm"
            aria-disabled={remove.isPending ? true : undefined}
            onClick={(event) => {
              event.preventDefault();
              void confirm();
            }}
          >
            {t("models.delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
