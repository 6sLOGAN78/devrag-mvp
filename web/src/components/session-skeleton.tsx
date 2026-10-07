import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { BareLayout } from "@/layouts/bare-layout";

export const SESSION_SKELETON_DELAY_MS = 150;

/** Shown while the session is being restored. Blank for the first 150 ms so a fast recovery never flashes. */
export function SessionSkeleton() {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), SESSION_SKELETON_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, []);
  return (
    <BareLayout>
      {visible ? (
        <div data-testid="session-skeleton" className="flex flex-col gap-4">
          <p role="status" className="sr-only">
            {t("session.restoring")}
          </p>
          <span aria-hidden="true" className="text-xl font-semibold leading-tight">
            {t("app.wordmark")}
          </span>
          <Skeleton className="h-4 w-full" aria-hidden="true" />
          <Skeleton className="h-4 w-4/5" aria-hidden="true" />
          <Skeleton className="h-4 w-3/5" aria-hidden="true" />
        </div>
      ) : null}
    </BareLayout>
  );
}
