import type { UseQueryResult } from "@tanstack/react-query";
import { Loader2, RefreshCw } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSystemStatusRequest } from "@/hooks/use-system-status-request";
import { ApiError } from "@/services/http";
import { dependencyOrder, type ServiceHealth } from "@/interfaces/health";
import { cn } from "@/lib/utils";

type OverallKind = "healthy" | "degraded" | "unreachable";

function overallOf(query: UseQueryResult<ServiceHealth>): OverallKind | "loading" {
  if (query.data) return query.data.kind === "ok" ? "healthy" : "degraded";
  if (query.isError) return "unreachable";
  return "loading";
}

function StatusBadge({ kind, testId }: { kind: OverallKind; testId?: string }) {
  const { t } = useTranslation();
  const label = t(`status.${kind}`);
  const dot = kind === "healthy" ? "bg-success" : "bg-destructive";
  return (
    <Badge variant={kind === "healthy" ? "success" : kind === "degraded" ? "degraded" : "destructive"} data-testid={testId}>
      {kind !== "unreachable" ? <span className={cn("size-2 rounded-full", dot)} aria-hidden="true" /> : null}
      {label}
    </Badge>
  );
}

function DependencyRows({ data }: { data: ServiceHealth["data"] }) {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-col gap-2">
      {dependencyOrder.map((name) => {
        const probe = data.checks[name];
        if (!probe) return null;
        const up = probe.status === "ok";
        return (
          <li key={name} data-testid={`status-dependency-${name}`} className="flex items-center justify-between gap-4">
            <span className="text-sm font-normal">{t(`status.dependencies.${name}`)}</span>
            <span className="flex items-center gap-2">
              <span className="font-mono text-xs tabular-nums text-muted-foreground">{t("status.elapsedMs", { ms: probe.elapsed_ms })}</span>
              <Badge variant={up ? "success" : "destructive"}>
                <span className={cn("size-2 rounded-full", up ? "bg-success" : "bg-destructive")} aria-hidden="true" />
                {up ? t("status.ok") : t("status.down")}
              </Badge>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

interface EngineCardProps {
  testId: string;
  title: string;
  query: UseQueryResult<ServiceHealth>;
  onRetry: () => void;
}

function EngineCard({ testId, title, query, onRetry }: EngineCardProps) {
  const { t } = useTranslation();
  const overall = overallOf(query);
  const updated = query.dataUpdatedAt > 0 ? new Date(query.dataUpdatedAt).toLocaleTimeString() : null;
  return (
    <Card data-testid={testId} aria-busy={query.isFetching}>
      <CardHeader className="flex-row items-center justify-between gap-4 space-y-0">
        {/* The overall badge reads first, then the engine name (focal order, checker flag 4). */}
        <div className="order-2 flex flex-col gap-1">
          <CardTitle>{title}</CardTitle>
        </div>
        <div className="order-1">{overall === "loading" ? <Skeleton className="h-6 w-20" /> : <StatusBadge kind={overall} testId={`${testId}-badge`} />}</div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {overall === "loading" ? (
          <div className="flex flex-col gap-2" role="status">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
            <p className="text-xs font-semibold text-muted-foreground">{t("status.loading")}</p>
          </div>
        ) : overall === "unreachable" ? (
          <ErrorState
            noun={t("status.errorNoun")}
            onAction={onRetry}
            code={query.error instanceof ApiError && query.error.code !== -1 ? query.error.code : undefined}
          />
        ) : query.data ? (
          <>
            <DependencyRows data={query.data.data} />
            <div className="flex flex-col gap-1 text-xs text-muted-foreground">
              <p>
                {t("status.sourceLabel")}:{" "}
                <span data-testid={`${testId}-source`} className="font-mono">
                  {query.data.source ?? query.data.data.engine}
                </span>
              </p>
              {updated ? <p>{t("status.updated", { time: updated })}</p> : null}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function SystemStatusPage() {
  const { t, i18n } = useTranslation();
  const { go, python, isFetching, refetch } = useSystemStatusRequest();
  useEffect(() => {
    document.title = t("status.pageTitle");
  }, [t, i18n.language]);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("status.title")}
        actions={
          <Button variant="secondary" onClick={() => void refetch()} aria-busy={isFetching}>
            {isFetching ? <Loader2 className="animate-spin" /> : <RefreshCw />}
            {t("status.refresh")}
          </Button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <EngineCard testId="status-card-go" title={t("status.goApi")} query={go} onRetry={() => void go.refetch()} />
        <EngineCard testId="status-card-python" title={t("status.pythonApi")} query={python} onRetry={() => void python.refetch()} />
      </div>
    </div>
  );
}
