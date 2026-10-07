import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

interface EmptyStateProps {
  icon?: LucideIcon;
  /** Name the thing: "No {noun} yet". Falls back to the generic heading. */
  noun?: string;
  heading?: string;
  body?: string;
  /** Large figure, for the Not Found variant. */
  display?: string;
  action?: ReactNode;
}

export function EmptyState({ icon: Icon, noun, heading, body, display, action }: EmptyStateProps) {
  const { t } = useTranslation();
  const title = heading ?? (noun ? t("emptyState.headingFor", { noun }) : t("emptyState.fallbackHeading"));
  return (
    <div data-testid="empty-state" className="flex flex-col items-center gap-2 py-12 text-center">
      {display ? <p className="text-display font-semibold leading-tight">{display}</p> : null}
      {Icon ? <Icon className="size-12 text-muted-foreground" aria-hidden="true" /> : null}
      <h1 className="text-xl font-semibold leading-tight">{title}</h1>
      {body ? <p className="max-w-md text-sm text-muted-foreground">{body}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
