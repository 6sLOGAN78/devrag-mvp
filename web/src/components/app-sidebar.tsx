import { NavLink } from "react-router";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { copy } from "@/constants/copy";
import { navEntries, pathSlug } from "@/constants/routes";
import { cn } from "@/lib/utils";

interface AppSidebarProps {
  /** Labels are always visible inside the mobile sheet; in the rail they collapse to tooltips. */
  forceLabels?: boolean;
  onNavigate?: () => void;
}

/** Navigation generated from the route registry: only entries that have `nav`. */
export function AppSidebar({ forceLabels = false, onNavigate }: AppSidebarProps) {
  const entries = navEntries();
  const labelClass = forceLabels ? "inline" : "hidden lg:inline";
  return (
    <nav aria-label={copy.a11y.primaryNav} className="flex flex-col gap-1">
      <p className={cn("px-2 pb-1 text-xs font-semibold text-muted-foreground", forceLabels ? "block" : "hidden lg:block")}>
        {copy.nav.groupCaption}
      </p>
      {entries.map((entry) => {
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
                <span className={labelClass}>{nav.label}</span>
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
              {nav.label}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </nav>
  );
}
