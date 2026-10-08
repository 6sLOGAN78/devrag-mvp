import { NavLink } from "react-router";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useTranslation } from "react-i18next";
import { NAV_GROUPS, navEntries, pathSlug, type NavGroup, type RouteEntry } from "@/constants/routes";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

/** Locale key of each group caption, written out so a missing key is a typo in one visible place. */
const GROUP_CAPTION_KEYS: Record<NavGroup, string> = { platform: "nav.groupPlatform", account: "nav.groupAccount" };

interface AppSidebarProps {
  /** Labels are always visible inside the mobile sheet; in the rail they collapse to tooltips. */
  forceLabels?: boolean;
  onNavigate?: () => void;
  /** Defaults to the route registry; overridable for tests. */
  entries?: readonly RouteEntry[];
}

/** Navigation generated from the route registry: only entries that have `nav`. */
export function AppSidebar({ forceLabels = false, onNavigate, entries: source }: AppSidebarProps) {
  const { t } = useTranslation();
  const entries = navEntries(source);
  const groups = NAV_GROUPS.map((group) => ({ group, items: entries.filter((e) => e.nav?.group === group) })).filter((g) => g.items.length > 0);
  const labelClass = forceLabels ? "inline" : "hidden lg:inline";
  const renderItem = (entry: RouteEntry) => {
    const nav = entry.nav;
    if (!nav) return null;
    const Icon = nav.icon;
    const link = (
      <NavLink
        to={entry.path}
        end={entry.path === "/"}
        onClick={onNavigate}
        data-testid={`nav-item-${pathSlug(entry.path)}`}
        className={({ isActive }) =>
          cn(
            "group relative flex min-h-10 items-center gap-2 rounded-md px-2 text-sm font-normal text-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
            isActive && "font-semibold",
          )
        }
      >
        {({ isActive }) => (
          <>
            {isActive ? <span data-testid="nav-active-indicator" className="absolute inset-y-1 left-0 w-0.5 rounded bg-primary" /> : null}
            <Icon className={cn("size-4 shrink-0", isActive ? "text-primary" : "text-muted-foreground")} aria-hidden="true" />
            <span className={labelClass}>{t(nav.labelKey)}</span>
          </>
        )}
      </NavLink>
    );
    return forceLabels ? (
      <div key={entry.path}>{link}</div>
    ) : (
      <Tooltip key={entry.path}>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent side="right" className="lg:hidden">
          {t(nav.labelKey)}
        </TooltipContent>
      </Tooltip>
    );
  };
  return (
    <nav aria-label={t("a11y.primaryNav")} className="flex flex-col gap-1">
      {groups.map(({ group, items }, index) => {
        const captionId = `nav-group-${group}`;
        return (
          <div key={group} role="group" aria-labelledby={captionId} className="flex flex-col gap-1">
            {index > 0 ? <Separator decorative={false} className={cn("my-1", forceLabels ? "hidden" : "lg:hidden")} /> : null}
            <p id={captionId} className={cn("px-2 pb-1 text-xs font-semibold text-muted-foreground", forceLabels ? "block" : "sr-only lg:not-sr-only lg:block", index > 0 && forceLabels && "pt-2", index > 0 && !forceLabels && "lg:pt-2")}>
              {t(GROUP_CAPTION_KEYS[group])}
            </p>
            {items.map((entry) => renderItem(entry))}
          </div>
        );
      })}
    </nav>
  );
}
