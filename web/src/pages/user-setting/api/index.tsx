import { KeyRound, Plus } from "lucide-react";
import { useEffect, useRef, useState, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApiTokensRequest, useCreateApiToken } from "@/hooks/use-api-token-request";
import { ApiError } from "@/services/http";
import { CreatedTokenDialog } from "./created-dialog";
import { notifyCreateFailure } from "./errors";
import { TokenRow } from "./token-row";

function CreateButton({ pending, onCreate, buttonRef }: { pending: boolean; onCreate: () => void; buttonRef: RefObject<HTMLButtonElement> }) {
  const { t } = useTranslation();
  return (
    <Button
      ref={buttonRef}
      type="button"
      data-testid="token-create"
      aria-disabled={pending ? true : undefined}
      aria-busy={pending ? true : undefined}
      className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
      onClick={onCreate}
    >
      <Plus aria-hidden="true" />
      {t("tokens.create")}
    </Button>
  );
}

function TokensSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="tokens-skeleton" className="flex flex-col gap-2 p-4">
      <p role="status" className="sr-only">
        {t("tokens.loading")}
      </p>
      <Skeleton className="h-10 w-full" aria-hidden="true" />
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} className="h-12 w-full" aria-hidden="true" />
      ))}
    </div>
  );
}

/**
 * API tokens page (UI-35). The list shows each token masked by default under the shared rule in `mask.ts`; reveal,
 * copy and delete are per row. Token values are rendered as text only and kept in the query cache and component
 * state: never in storage, the URL, the title, a toast or the console. Only the workspace owner can manage tokens;
 * any other member gets a 403 from the list and sees the owner-only state with no token data.
 */
export default function ApiTokensPage() {
  const { t, i18n } = useTranslation();
  const tokens = useApiTokensRequest();
  const create = useCreateApiToken();
  const [created, setCreated] = useState<string | null>(null);
  const [focusRequest, setFocusRequest] = useState(0);
  const createButton = useRef<HTMLButtonElement>(null);
  const caption = useRef<HTMLTableCaptionElement>(null);

  useEffect(() => {
    document.title = t("tokens.pageTitle");
  }, [t, i18n.language]);

  // After a delete the row is gone: focus moves to the table caption, or to the Create button once the list is empty.
  useEffect(() => {
    if (focusRequest === 0) return;
    (caption.current ?? createButton.current)?.focus();
  }, [focusRequest]);

  async function onCreate(): Promise<void> {
    if (create.isPending) return;
    try {
      const token = await create.mutateAsync();
      create.reset();
      setCreated(token.token);
    } catch (error) {
      notifyCreateFailure(error);
    }
  }

  const list = tokens.data;
  const forbidden = tokens.error instanceof ApiError && tokens.error.status === 403;
  const hasTokens = list !== undefined && list.length > 0;
  const createControl = <CreateButton pending={create.isPending} onCreate={() => void onCreate()} buttonRef={createButton} />;

  let body;
  if (tokens.isPending) {
    body = <TokensSkeleton />;
  } else if (forbidden) {
    body = (
      <div data-testid="tokens-forbidden" className="p-6">
        <ErrorState heading={t("tokens.forbidden.heading")} body={t("tokens.forbidden.body")} />
      </div>
    );
  } else if (tokens.isError) {
    body = (
      <div className="p-6">
        <ErrorState noun={t("tokens.errorNoun")} onAction={() => void tokens.refetch()} />
      </div>
    );
  } else if (!hasTokens) {
    body = <EmptyState as="h2" icon={KeyRound} heading={t("tokens.empty.heading")} body={t("tokens.empty.body")} action={createControl} />;
  } else {
    body = (
      <Table data-testid="tokens-table">
        <TableCaption ref={caption} tabIndex={-1}>
          {t("tokens.title")}
        </TableCaption>
        <TableHeader>
          <TableRow className="h-10">
            <TableHead>{t("tokens.col.token")}</TableHead>
            <TableHead>{t("tokens.col.created")}</TableHead>
            <TableHead>{t("tokens.col.actions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {list.map((token) => (
            <TokenRow key={token.token} token={token} onDeleted={() => setFocusRequest((n) => n + 1)} />
          ))}
        </TableBody>
      </Table>
    );
  }

  return (
    <div data-testid="tokens-page" className="flex flex-col gap-6">
      <PageHeader title={t("tokens.title")} actions={hasTokens ? createControl : undefined} />
      <p className="max-w-prose text-sm font-normal text-muted-foreground">{t("tokens.intro")}</p>
      <Card>
        <CardContent className="p-0">{body}</CardContent>
      </Card>
      <CreatedTokenDialog token={created} onClose={() => setCreated(null)} returnFocusTo={createButton} />
    </div>
  );
}
