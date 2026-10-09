import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { clearMutation, useAddModelRequest, useModelTenantId } from "@/hooks/use-llm-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { notifySuccess } from "@/services/notify";
import { DialogShell, FailureAlert, PendingStatus, SubmitFooter } from "./dialog-parts";
import { isAborted, providerErrorKey, type ProviderFailure } from "./errors";
import { providerName, type ProviderSpec } from "./providers";
import { addModelSchema, type AddModelValues } from "./schemas";

interface AddModelDialogProps {
  spec: ProviderSpec;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCloseAutoFocus: (event: Event) => void;
}

function AddModelForm({ spec, pendingRef, close }: { spec: ProviderSpec; pendingRef: MutableRefObject<boolean>; close: () => void }) {
  const { t } = useTranslation();
  const tenantId = useModelTenantId();
  const workspace = useActiveWorkspace()?.name ?? "";
  const add = useAddModelRequest();
  const name = providerName(spec, t);
  const form = useForm<AddModelValues>({
    resolver: zodResolver(addModelSchema),
    mode: "onSubmit",
    reValidateMode: "onChange",
    defaultValues: { modelId: "", type: "chat" },
  });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ProviderFailure | null>(null);
  const inFlight = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      controller.current?.abort();
      pendingRef.current = false;
      add.reset();
    },
    [],
  );

  async function onSubmit(values: AddModelValues): Promise<void> {
    if (inFlight.current || tenantId === null) return;
    inFlight.current = true;
    pendingRef.current = true;
    setBusy(true);
    setFailure(null);
    const abort = new AbortController();
    controller.current = abort;
    try {
      await add.mutateAsync({ input: { tenantId, provider: spec.slug, model: { name: values.modelId.trim(), type: values.type } }, signal: abort.signal });
      notifySuccess(t("models.modelAdded"));
      close();
    } catch (error) {
      if (isAborted(error)) return;
      setFailure(providerErrorKey(error));
    } finally {
      inFlight.current = false;
      pendingRef.current = false;
      controller.current = null;
      setBusy(false);
      clearMutation(add);
    }
  }

  return (
    <Form {...form}>
      <form data-testid="add-model-form" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <FormField
          control={form.control}
          name="modelId"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("models.field.modelId")}</FormLabel>
              <FormControl>
                <Input {...field} data-testid="field-model-id" autoComplete="off" spellCheck={false} readOnly={busy} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("models.field.modelType")}</FormLabel>
              <FormControl>
                <NativeSelect {...field} data-testid="field-model-type" disabled={busy}>
                  <option value="chat">{t("models.type.chat")}</option>
                  <option value="embedding">{t("models.type.embedding")}</option>
                </NativeSelect>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        {busy ? <PendingStatus /> : null}
        {failure === null ? null : <FailureAlert failure={failure} provider={name} workspace={workspace} />}
        <SubmitFooter busy={busy} />
      </form>
    </Form>
  );
}

/**
 * Add a model to a configured provider (UI-SPEC "Add model dialog"). The server tests the model with the saved
 * credentials and records an embedding model's dimension; there is no key field because the saved key is used. There is
 * no per-model remove in this phase: a mistyped model is never stored because its test fails.
 */
export function AddModelDialog({ spec, open, onOpenChange, onCloseAutoFocus }: AddModelDialogProps) {
  const { t } = useTranslation();
  const pendingRef = useRef(false);
  return (
    <DialogShell
      open={open}
      onOpenChange={onOpenChange}
      onCloseAutoFocus={onCloseAutoFocus}
      pendingRef={pendingRef}
      title={t("models.dialog.addModelTitle", { provider: providerName(spec, t) })}
    >
      <AddModelForm spec={spec} pendingRef={pendingRef} close={() => onOpenChange(false)} />
    </DialogShell>
  );
}
