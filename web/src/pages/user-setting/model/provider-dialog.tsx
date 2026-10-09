import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { useForm, type FieldPath } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/password-input";
import { clearMutation, useDefaultsRequest, useModelTenantId, useSaveProviderRequest } from "@/hooks/use-llm-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { notifySuccess } from "@/services/notify";
import { registeredModelFor, type ProviderView, type RegisteredModel } from "@/services/model-service";
import { DialogShell, FailureAlert, PendingStatus, SubmitFooter } from "./dialog-parts";
import { isAborted, providerErrorKey, type ProviderFailure } from "./errors";
import { providerName, type ProviderSpec } from "./providers";
import { currentInstance, providerSchema, type ProviderFormValues, type ProviderMode } from "./schemas";

interface ProviderDialogProps {
  spec: ProviderSpec;
  /** `setup` registers a provider with its first models; `change` replaces the key and/or address of a configured one. */
  mode: ProviderMode;
  /** What the API returned for this provider. The change dialogs read the stored address and the models from it. */
  current: ProviderView | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCloseAutoFocus: (event: Event) => void;
}

interface FieldProps {
  name: FieldPath<ProviderFormValues>;
  label: string;
  testId: string;
  busy: boolean;
  help?: string;
  secret?: boolean;
  url?: boolean;
}

/** One labelled input. The typed key goes through `PasswordInput` (hidden by default) with every autofill and spellcheck opt-out. */
function ProviderField({ name, label, testId, busy, help, secret = false, url = false }: FieldProps) {
  return (
    <FormField<ProviderFormValues>
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            {secret ? (
              <PasswordInput
                {...field}
                name="provider_key"
                data-testid={testId}
                autoComplete="off"
                spellCheck={false}
                data-1p-ignore
                data-lpignore="true"
                readOnly={busy}
              />
            ) : (
              <Input {...field} data-testid={testId} autoComplete="off" spellCheck={false} inputMode={url ? "url" : undefined} readOnly={busy} />
            )}
          </FormControl>
          {help === undefined ? null : <FormDescription>{help}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

/** The models a set up sends: whichever of the chat and embedding fields were filled. */
function setupModels(values: ProviderFormValues): RegisteredModel[] {
  const models: RegisteredModel[] = [];
  if (values.chatModel.trim() !== "") models.push({ name: values.chatModel.trim(), type: "chat" });
  if (values.embeddingModel.trim() !== "") models.push({ name: values.embeddingModel.trim(), type: "embedding" });
  return models;
}

/** True when a default of a type the call just added is still unset: the toast then points at the defaults. */
function lacksDefault(models: RegisteredModel[], defaults: { chat: string; embedding: string } | undefined): boolean {
  if (defaults === undefined) return false;
  return models.some((model) => (model.type === "chat" ? defaults.chat === "" : defaults.embedding === ""));
}

interface FormProps extends Pick<ProviderDialogProps, "spec" | "mode" | "current"> {
  pendingRef: MutableRefObject<boolean>;
  close: () => void;
}

/**
 * The form of the set up and change dialogs. It lives inside the dialog content, so it is mounted only while the
 * dialog is open: closing, Esc and success all unmount it, which drops the typed key from form state. The request is
 * aborted on unmount (Esc and Close during a call; the server stores only after a passing test, so nothing is saved).
 * The mutation is reset in a `finally`, so the key leaves the mutation cache the moment the call settles.
 */
function ProviderForm({ spec, mode, current, pendingRef, close }: FormProps) {
  const { t } = useTranslation();
  const tenantId = useModelTenantId();
  const workspace = useActiveWorkspace()?.name ?? "";
  const defaults = useDefaultsRequest();
  const save = useSaveProviderRequest();
  const name = providerName(spec, t);
  const stored = currentInstance(current);
  const resolver = useMemo(() => zodResolver(providerSchema(spec, mode, current)), [spec, mode, current]);
  const form = useForm<ProviderFormValues>({
    resolver,
    mode: "onSubmit",
    reValidateMode: "onChange",
    defaultValues: {
      apiKey: "",
      baseUrl: mode === "change" ? (stored?.baseUrl ?? "") : "",
      apiVersion: mode === "change" ? (stored?.apiVersion ?? "") : "",
      chatModel: "",
      embeddingModel: "",
    },
  });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ProviderFailure | null>(null);
  const inFlight = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      // Close, Esc, success or a workspace switch: stop the call and forget everything typed.
      controller.current?.abort();
      pendingRef.current = false;
      form.reset();
      save.reset();
    },
    [],
  );

  async function onSubmit(values: ProviderFormValues): Promise<void> {
    if (inFlight.current || tenantId === null) return;
    const models = mode === "setup" ? setupModels(values) : registeredModelFor(current);
    setFailure(null);
    if (models.length === 0) {
      setFailure({ key: "models.refused.generic", refusal: false });
      return;
    }
    inFlight.current = true;
    pendingRef.current = true;
    setBusy(true);
    const abort = new AbortController();
    controller.current = abort;
    try {
      await save.mutateAsync({
        input: {
          tenantId,
          provider: spec.slug,
          apiKey: spec.fields.key === "none" ? undefined : values.apiKey.trim(),
          baseUrl: spec.fields.baseUrl === "required" ? values.baseUrl.trim() : undefined,
          apiVersion: spec.fields.apiVersion ? values.apiVersion.trim() : undefined,
          models,
        },
        signal: abort.signal,
      });
      form.reset();
      const hint = mode === "setup" && lacksDefault(models, defaults.data);
      notifySuccess(t(mode === "setup" ? "models.saved" : "models.updated", { provider: name }), hint ? t("models.savedHint") : undefined);
      close();
    } catch (error) {
      if (isAborted(error)) return;
      const answer = providerErrorKey(error);
      if (answer.field === "key") {
        form.setError("apiKey", { type: "server", message: answer.key });
        form.setFocus("apiKey");
      } else {
        setFailure(answer);
      }
    } finally {
      inFlight.current = false;
      pendingRef.current = false;
      controller.current = null;
      setBusy(false);
      clearMutation(save);
    }
  }

  const keyHelp = (): string | undefined => {
    if (spec.fields.key === "optional") return t(mode === "change" ? "models.help.keyNotReused" : "models.help.optionalKey");
    if (mode === "change" && (stored?.last4 ?? "") !== "") return t("models.help.replaceKey", { last4: stored?.last4 });
    return undefined;
  };

  return (
    <Form {...form}>
      <form data-testid="provider-form" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        {spec.fields.baseUrl === "required" ? (
          <ProviderField
            name="baseUrl"
            label={t(spec.fields.baseUrlLabelKey)}
            testId="field-base-url"
            busy={busy}
            url
            help={spec.slug === "ollama" ? t("models.help.ollamaUrl") : undefined}
          />
        ) : null}
        {spec.fields.apiVersion ? <ProviderField name="apiVersion" label={t("models.field.apiVersion")} testId="field-api-version" busy={busy} /> : null}
        {spec.fields.key === "none" ? null : <ProviderField name="apiKey" label={t("models.field.key")} testId="field-provider-key" busy={busy} secret help={keyHelp()} />}
        {mode === "setup" ? (
          <>
            <ProviderField
              name="chatModel"
              label={t(spec.fields.chatLabelKey)}
              testId="field-chat-model"
              busy={busy}
              help={t("models.help.modelId", { example: spec.modelExamples[0] })}
            />
            <ProviderField
              name="embeddingModel"
              label={t(spec.fields.embeddingLabelKey)}
              testId="field-embedding-model"
              busy={busy}
              help={t("models.help.modelId", { example: spec.modelExamples[1] })}
            />
          </>
        ) : null}
        {busy ? <PendingStatus /> : null}
        {failure === null ? null : <FailureAlert failure={failure} provider={name} workspace={workspace} />}
        <SubmitFooter busy={busy} />
      </form>
    </Form>
  );
}

/**
 * Set up, Change key and Change address (UI-37, D-15 to D-17). One dialog, three jobs: the fields follow the provider
 * table; the primary button is "Test and save" and nothing is stored unless the server's real test passes. A refusal is
 * shown inline and never touches the session. Change mode renders no model field and sends one registered model.
 */
export function ProviderDialog({ spec, mode, current, open, onOpenChange, onCloseAutoFocus }: ProviderDialogProps) {
  const { t } = useTranslation();
  const pendingRef = useRef(false);
  const name = providerName(spec, t);
  const title =
    mode === "setup" ? t("models.dialog.setUpTitle", { provider: name }) : t(spec.slug === "ollama" ? "models.dialog.changeAddressTitle" : "models.dialog.changeKeyTitle", { provider: name });
  return (
    <DialogShell open={open} onOpenChange={onOpenChange} onCloseAutoFocus={onCloseAutoFocus} pendingRef={pendingRef} title={title}>
      <ProviderForm spec={spec} mode={mode} current={current} pendingRef={pendingRef} close={() => onOpenChange(false)} />
    </DialogShell>
  );
}
