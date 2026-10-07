import { Check, Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { setLanguage } from "@/i18n";

// Endonyms: each name is shown in its own language and is never translated, so each item carries its own lang.
const LANGUAGES = [
  { code: "en", endonym: "English" },
  { code: "zh", endonym: "中文" },
] as const;

/** Applies at once, persists to localStorage and sets <html lang>; no toast. Writing user.language comes with the profile endpoint (plan 02-16). */
export function LanguageSwitch() {
  const { t, i18n } = useTranslation();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("header.language")} data-testid="language-switch">
          <Languages aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {LANGUAGES.map(({ code, endonym }) => (
          <DropdownMenuItem key={code} lang={code} data-testid={`language-option-${code}`} onSelect={() => void setLanguage(code)}>
            <span className="flex-1">{endonym}</span>
            {i18n.language === code ? <Check data-testid="language-current" aria-hidden="true" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
