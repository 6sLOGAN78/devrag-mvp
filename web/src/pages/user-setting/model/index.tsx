import { Cpu } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Alert } from "@/components/ui/alert";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDefaultsRequest, useProvidersRequest } from "@/hooks/use-llm-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { AddModelDialog } from "./add-model-dialog";
import { DeleteProviderDialog } from "./delete-provider-dialog";
import { ProviderDialog } from "./provider-dialog";
import { ProviderRow, type RowAction } from "./provider-row";
import { PROVIDERS, type ProviderSpec } from "./providers";

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

interface OpenDialog {
  action: RowAction;
  spec: ProviderSpec;
}

/**
 * Model settings (UI-37). Shows the active workspace's five providers and their models. Owners and admins also see
 * the credential line (the masked key tail and the address the server supplied); members see neither and only the
 * configured providers. The data keys on the active workspace, so switching workspace changes the page (D-26). The
 * SPA never holds a saved key. The role only decides what is drawn: the server answers every request on its own
 * authority.
 *
 * The write dialogs (set up, change key or address, add model, delete) are opened from the row buttons, which exist for
 * owners and admins only. Their state lives here so that focus can return to the right place when one closes.
 */
export default function ModelsPage() {
  const { t, i18n } = useTranslation();
  const workspace = useActiveWorkspace();
  const providers = useProvidersRequest();
  const defaults = useDefaultsRequest();
  const elevated = workspace?.role === "owner" || workspace?.role === "admin";
  const tenantId = workspace?.tenantId ?? null;
  const [dialog, setDialog] = useState<OpenDialog | null>(null);
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLElement | null>(null);
  const list = useRef<HTMLUListElement | null>(null);
  const title = useRef<HTMLHeadingElement | null>(null);
  const focusTitle = useRef(false);

  // A dialog belongs to one workspace and one role: switching either closes it and drops what was typed.
  useEffect(() => {
    setOpen(false);
    setDialog(null);
  }, [tenantId, elevated]);

  useEffect(() => {
    document.title = t("models.documentTitle");
  }, [t, i18n.language]);

  const byName = new Map((providers.data ?? []).map((provider) => [provider.slug, provider]));
  const visible = elevated ? PROVIDERS : PROVIDERS.filter((spec) => byName.get(spec.slug)?.configured === true);

  function openDialog(action: RowAction, slug: string, element: HTMLElement): void {
    const spec = PROVIDERS.find((candidate) => candidate.slug === slug);
    if (spec === undefined) return;
    trigger.current = element;
    focusTitle.current = false;
    setDialog({ action, spec });
    setOpen(true);
  }

  /** Back to the button that opened the dialog; if it is gone (Set up became Add model) the row's first button; after a delete, the card title. */
  function restoreFocus(event: Event): void {
    event.preventDefault();
    const slug = dialog?.spec.slug;
    const fallback = slug === undefined ? null : list.current?.querySelector<HTMLElement>(`[data-testid="provider-row-${slug}"] button`);
    const target = focusTitle.current ? title.current : trigger.current?.isConnected === true ? trigger.current : (fallback ?? title.current);
    target?.focus();
  }

  const current = dialog === null ? undefined : byName.get(dialog.spec.slug);

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
      <ul ref={list} data-testid="providers-list" className="divide-y">
        {visible.map((spec) => (
          <ProviderRow key={spec.slug} spec={spec} provider={byName.get(spec.slug)} defaults={defaults.data} elevated={elevated} onAction={elevated ? openDialog : undefined} />
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
          <CardTitle ref={title} tabIndex={-1} data-testid="providers-title" className="rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {t("models.providers.title")}
          </CardTitle>
        </CardHeader>
        {body}
      </Card>
      {elevated && dialog !== null && (dialog.action === "setup" || dialog.action === "change") ? (
        <ProviderDialog spec={dialog.spec} mode={dialog.action === "setup" ? "setup" : "change"} current={current} open={open} onOpenChange={setOpen} onCloseAutoFocus={restoreFocus} />
      ) : null}
      {elevated && dialog !== null && dialog.action === "add" ? <AddModelDialog spec={dialog.spec} open={open} onOpenChange={setOpen} onCloseAutoFocus={restoreFocus} /> : null}
      {elevated && dialog !== null && dialog.action === "delete" ? (
        <DeleteProviderDialog
          spec={dialog.spec}
          modelCount={current?.models.length ?? 0}
          open={open}
          onOpenChange={setOpen}
          onDeleted={() => {
            focusTitle.current = true;
          }}
          onCloseAutoFocus={restoreFocus}
        />
      ) : null}
    </div>
  );
}
