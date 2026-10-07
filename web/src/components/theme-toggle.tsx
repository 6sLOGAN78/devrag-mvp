import { Monitor, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useTranslation } from "react-i18next";
import { setThemeChoice, type ThemeChoice } from "@/utils/theme";

const items: { choice: ThemeChoice; icon: typeof Sun }[] = [
  { choice: "light", icon: Sun },
  { choice: "dark", icon: Moon },
  { choice: "system", icon: Monitor },
];

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
          <DropdownMenuItem key={choice} onSelect={() => setThemeChoice(choice)}>
            <Icon />
            {t(`theme.${choice}`)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
