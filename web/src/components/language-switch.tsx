import { Check, Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { saveSettingQuietly } from "@/hooks/use-profile-request";
import { setLanguage } from "@/i18n";

// Endonyms: each name is shown in its own language and is never translated, so each item carries its own lang.
const LANGUAGES = [
  { code: "en", endonym: "English" },
  { code: "zh", endonym: "中文" },
] as const;

/**
 * Applies at once, persists to localStorage and sets <html lang>; no toast. For a signed-in user the choice is also
 * written to `user.language`, best effort and silent: a failed write never changes or announces anything.
 */
async function choose(code: string): Promise<void> {
  const lang = await setLanguage(code);
  await saveSettingQuietly({ language: lang });
}

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
          <DropdownMenuItem key={code} lang={code} data-testid={`language-option-${code}`} onSelect={() => void choose(code)}>
            <span className="flex-1">{endonym}</span>
            {i18n.language === code ? <Check data-testid="language-current" aria-hidden="true" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
