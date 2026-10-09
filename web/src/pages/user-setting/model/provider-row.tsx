import { CircleCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import type { DefaultsView, InstanceView, ModelView, ProviderView } from "@/services/model-service";
import { providerName, type ProviderSpec } from "./providers";
import { maskSecret } from "./secret-mask";

interface ProviderRowProps {
  spec: ProviderSpec;
  /** What the API returned for this provider; undefined if the list had no entry for it. */
  provider: ProviderView | undefined;
  defaults: DefaultsView | undefined;
  /** Owner or admin of the active workspace. Only they see the credential line (D-17). */
  elevated: boolean;
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
 * One provider of the workspace: name, status, description, the credential line for owners and admins and the models
 * it serves. Every string from the server renders as a text node. This plan renders no action; the set up, add model,
 * change key and delete controls mount in the actions slot of this row in plan 03-21.
 */
export function ProviderRow({ spec, provider, defaults, elevated }: ProviderRowProps) {
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
