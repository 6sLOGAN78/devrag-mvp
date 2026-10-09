import { CircleCheck, Trash2 } from "lucide-react";
import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DefaultsView, InstanceView, ModelView, ProviderView } from "@/services/model-service";
import { providerName, type ProviderSpec } from "./providers";
import { maskSecret } from "./secret-mask";

/** What a row button asks the page to open. */
export type RowAction = "setup" | "add" | "change" | "delete";

interface ProviderRowProps {
  spec: ProviderSpec;
  /** What the API returned for this provider; undefined if the list had no entry for it. */
  provider: ProviderView | undefined;
  defaults: DefaultsView | undefined;
  /** Owner or admin of the active workspace. Only they see the credential line (D-17). */
  elevated: boolean;
  /** Opens a dialog for this provider. `trigger` is the button, so the page can return focus to it. Absent for members. */
  onAction?: (action: RowAction, slug: string, trigger: HTMLElement) => void;
}

function CredentialLine({ spec, instance }: { spec: ProviderSpec; instance: InstanceView }) {
  const { t } = useTranslation();
  // Ollama has no key; the server gives an empty or missing tail for a provider that stores none.
  const showKey = spec.fields.key !== "none" && instance.last4 !== null && instance.last4 !== "";
  const showAddress = instance.baseUrl !== null && instance.baseUrl !== "";
  if (!showKey && !showAddress) return null;
  return (
    <div data-testid="provider-credentials" className="flex flex-col gap-1 text-sm sm:flex-row sm:flex-wrap sm:gap-x-6">
      {showKey ? (
        <p className="flex min-w-0 flex-wrap items-baseline gap-2">
          <span className="text-xs font-semibold">{t("models.credential.key")}</span>
          <span data-testid="provider-mask" className="font-mono">
            {maskSecret(instance.last4 ?? "")}
          </span>
        </p>
      ) : null}
      {showAddress ? (
        <p className="flex min-w-0 flex-wrap items-baseline gap-2">
          <span className="text-xs font-semibold">{t("models.credential.baseUrl")}</span>
          <span className="break-all font-mono">{instance.baseUrl}</span>
        </p>
      ) : null}
    </div>
  );
}

function isDefault(model: ModelView, defaults: DefaultsView | undefined): "chat" | "embedding" | null {
  if (defaults === undefined) return null;
  if (model.type === "chat" && defaults.chat === model.id) return "chat";
  if (model.type === "embedding" && defaults.embedding === model.id) return "embedding";
  return null;
}

function ModelRow({ model, defaults }: { model: ModelView; defaults: DefaultsView | undefined }) {
  const { t } = useTranslation();
  const chosen = isDefault(model, defaults);
  return (
    <li data-testid="model-row" className="flex flex-wrap items-center gap-2 text-sm">
      <span className="break-all font-mono">{model.name}</span>
      <Badge>{model.type === "embedding" ? t("models.type.embedding") : t("models.type.chat")}</Badge>
      {model.type === "embedding" && model.dimension !== null ? <span className="text-xs font-normal tabular-nums text-muted-foreground">{t("models.dimensions", { count: model.dimension })}</span> : null}
      {chosen !== null ? <Badge variant="outline">{chosen === "chat" ? t("models.badge.defaultChat") : t("models.badge.defaultEmbedding")}</Badge> : null}
    </li>
  );
}

/**
 * The row's write controls (owner and admin only; members get no button at all, not a disabled one). Not configured:
 * Set up. Configured: Add model, Change key (Change address for Ollama, which has no key) and Delete. Each accessible
 * name carries the provider, because the visible text alone ("Set up") repeats on every row.
 */
function RowActions({ spec, name, configured, onAction }: { spec: ProviderSpec; name: string; configured: boolean; onAction: NonNullable<ProviderRowProps["onAction"]> }) {
  const { t } = useTranslation();
  const open = (action: RowAction) => (event: MouseEvent<HTMLButtonElement>) => onAction(action, spec.slug, event.currentTarget);
  if (!configured) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" data-testid="provider-setup" aria-label={t("models.action.setUpLabel", { provider: name })} onClick={open("setup")}>
          {t("models.action.setUp")}
        </Button>
      </div>
    );
  }
  const keyless = spec.fields.key === "none";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button type="button" variant="outline" data-testid="provider-add-model" aria-label={t("models.action.addModelLabel", { provider: name })} onClick={open("add")}>
        {t("models.action.addModel")}
      </Button>
      <Button
        type="button"
        variant="ghost"
        data-testid="provider-change"
        aria-label={t(keyless ? "models.action.changeAddressLabel" : "models.action.changeKeyLabel", { provider: name })}
        onClick={open("change")}
      >
        {t(keyless ? "models.action.changeAddress" : "models.action.changeKey")}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        data-testid="provider-delete"
        aria-label={t("models.action.deleteLabel", { provider: name })}
        className="hover:text-destructive focus-visible:text-destructive"
        onClick={open("delete")}
      >
        <Trash2 aria-hidden="true" />
      </Button>
    </div>
  );
}

/**
 * One provider of the workspace: name, status, description, the credential line for owners and admins, the models it
 * serves and, for owners and admins, the write controls. Every string from the server renders as a text node.
 */
export function ProviderRow({ spec, provider, defaults, elevated, onAction }: ProviderRowProps) {
  const { t } = useTranslation();
  const name = providerName(spec, t);
  const configured = provider?.configured === true;
  const instances = configured ? (provider?.instances.filter((instance) => instance.configured) ?? []) : [];
  const models = provider?.models ?? [];
  return (
    <li data-testid={`provider-row-${spec.slug}`} className="flex flex-col gap-2 px-6 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{name}</h3>
        <Badge data-testid="provider-status" variant={configured ? "success" : "default"}>
          {configured ? <CircleCheck className="size-3" aria-hidden="true" /> : null}
          {configured ? t("models.status.configured") : t("models.status.notConfigured")}
        </Badge>
      </div>
      <p className="text-sm font-normal text-muted-foreground">{t(spec.descriptionKey)}</p>
      {elevated && onAction !== undefined ? <RowActions spec={spec} name={name} configured={configured} onAction={onAction} /> : null}
      {elevated ? instances.map((instance) => <CredentialLine key={instance.name} spec={spec} instance={instance} />) : null}
      {models.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {models.map((model) => (
            <ModelRow key={model.id} model={model} defaults={defaults} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}
