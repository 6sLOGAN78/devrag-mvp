import { Monitor, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { copy } from "@/constants/copy";
import { setThemeChoice, type ThemeChoice } from "@/utils/theme";

const items: { choice: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { choice: "light", label: copy.theme.light, icon: Sun },
  { choice: "dark", label: copy.theme.dark, icon: Moon },
  { choice: "system", label: copy.theme.system, icon: Monitor },
];

export function ThemeToggle() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={copy.theme.label} data-testid="theme-toggle">
          <Sun className="size-4 dark:hidden" />
          <Moon className="hidden size-4 dark:block" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {items.map(({ choice, label, icon: Icon }) => (
          <DropdownMenuItem key={choice} onSelect={() => setThemeChoice(choice)}>
            <Icon />
            {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
