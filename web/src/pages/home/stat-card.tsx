import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";

interface StatCardProps {
  testId: string;
  caption: string;
  to: string;
  isPending?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  /** The value shown once loaded. */
  value: string | number;
}

/**
 * One home stat (UI-09): a whole-card link with a caption and a tabular value, its own loading skeleton and its own
 * error with a retry that re-runs only that card's query. A failure here never affects another card.
 */
export function StatCard({ testId, caption, to, isPending = false, isError = false, onRetry, value }: StatCardProps) {
  const { t } = useTranslation();
  const label = <span className="text-sm font-semibold text-muted-foreground">{caption}</span>;
  if (isPending) {
    return (
      <Card data-testid={testId}>
        <CardContent className="flex flex-col gap-2 p-6">
          {label}
          <Skeleton className="h-7 w-12" aria-hidden="true" />
        </CardContent>
      </Card>
    );
  }
  if (isError) {
    return (
      <Card data-testid={testId}>
        <CardContent className="flex flex-col items-start gap-2 p-6">
          {label}
          <span className="text-sm text-muted-foreground">{t("home.stat.loadError")}</span>
          <Button type="button" variant="outline" size="sm" data-testid={`${testId}-retry`} onClick={onRetry}>
            {t("home.stat.retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card data-testid={testId}>
      <Link to={to} className={`block rounded-lg ${FOCUS_RING}`}>
        <CardContent className="flex flex-col gap-1 p-6">
          {label}
          <span className="text-xl font-semibold leading-tight tabular-nums">{value}</span>
        </CardContent>
      </Link>
    </Card>
  );
}
