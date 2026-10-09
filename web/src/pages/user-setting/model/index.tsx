import { Cpu } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDefaultsRequest, useProvidersRequest } from "@/hooks/use-llm-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { ProviderRow } from "./provider-row";
import { PROVIDERS } from "./providers";

function ProvidersSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="providers-skeleton" className="flex flex-col gap-2 p-4">
      <p role="status" className="sr-only">
        {t("models.loading")}
      </p>
      {PROVIDERS.map((spec) => (
        <Skeleton key={spec.slug} className="h-16 w-full" aria-hidden="true" />
      ))}
    </div>
  );
}

/**
 * Model settings (UI-37). Shows the active workspace's five providers and their models. Owners and admins also see
 * the credential line (the masked key tail and the address the server supplied); members see neither and only the
 * configured providers. The data keys on the active workspace, so switching workspace changes the page (D-26). The
 * SPA never holds a saved key. The role only decides what is drawn: the server answers every request on its own
 * authority.
 */
export default function ModelsPage() {
  const { t, i18n } = useTranslation();
  const workspace = useActiveWorkspace();
  const providers = useProvidersRequest();
  const defaults = useDefaultsRequest();
  const elevated = workspace?.role === "owner" || workspace?.role === "admin";

  useEffect(() => {
    document.title = t("models.documentTitle");
  }, [t, i18n.language]);

  const byName = new Map((providers.data ?? []).map((provider) => [provider.slug, provider]));
  const visible = elevated ? PROVIDERS : PROVIDERS.filter((spec) => byName.get(spec.slug)?.configured === true);

  let body;
  if (providers.isPending) {
    body = <ProvidersSkeleton />;
  } else if (providers.isError) {
    body = (
      <div className="p-6">
        <ErrorState noun={t("models.errorNoun.providers")} onAction={() => void providers.refetch()} />
      </div>
    );
  } else if (visible.length === 0) {
    body = <EmptyState as="h2" icon={Cpu} heading={t("models.empty.heading")} body={t("models.empty.body")} />;
  } else {
    body = (
      <ul data-testid="providers-list" className="divide-y">
        {visible.map((spec) => (
          <ProviderRow key={spec.slug} spec={spec} provider={byName.get(spec.slug)} defaults={defaults.data} elevated={elevated} />
        ))}
      </ul>
    );
  }

  return (
    <div data-testid="models-page" className="flex flex-col gap-6">
      <PageHeader title={t("models.title")} />
      <p className="max-w-prose text-sm font-normal text-muted-foreground">{t("models.intro", { workspace: workspace?.name ?? "" })}</p>
      {!elevated && workspace !== null ? (
        <Alert variant="info" data-testid="models-readonly-notice">
          {t("models.readOnly")}
        </Alert>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>{t("models.providers.title")}</CardTitle>
        </CardHeader>
        {body}
      </Card>
    </div>
  );
}
