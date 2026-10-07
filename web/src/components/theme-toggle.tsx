import { Monitor, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useTranslation } from "react-i18next";
import { saveSettingQuietly } from "@/hooks/use-profile-request";
import { colourSchemaFor, setThemeChoice, type ThemeChoice } from "@/utils/theme";

const items: { choice: ThemeChoice; icon: typeof Sun }[] = [
  { choice: "light", icon: Sun },
  { choice: "dark", icon: Moon },
  { choice: "system", icon: Monitor },
];

/** Applies and stores the choice at once; for a signed-in user Bright or Dark is also written to the profile, best effort and silent. */
function select(choice: ThemeChoice): void {
  setThemeChoice(choice);
  const schema = colourSchemaFor(choice);
  if (schema !== null) void saveSettingQuietly({ color_schema: schema });
}

export function ThemeToggle() {
  const { t } = useTranslation();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("theme.label")} data-testid="theme-toggle">
          <Sun className="size-4 dark:hidden" />
          <Moon className="hidden size-4 dark:block" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {items.map(({ choice, icon: Icon }) => (
          <DropdownMenuItem key={choice} onSelect={() => select(choice)}>
            <Icon />
            {t(`theme.${choice}`)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
