export type Language = "en" | "zh";

export const LANG_KEY = "devrag.lang";
export const LANGUAGES: readonly Language[] = ["en", "zh"];

/** Accepts codes (en, zh-CN) and the legacy labels (English, Chinese); anything else is English. */
export function normalizeLanguage(value: string | null | undefined): Language {
  const v = (value ?? "").trim().toLowerCase();
  return v === "zh" || v.startsWith("zh-") || v === "chinese" ? "zh" : "en";
}

export interface DetectInput {
  userLanguage?: string | null;
  stored?: string | null;
  navigatorLanguage?: string | null;
}

/** Order: signed-in user language, stored choice, browser language, English. */
export function detectLanguage({ userLanguage, stored, navigatorLanguage }: DetectInput): Language {
  const first = [userLanguage, stored, navigatorLanguage].find((v) => v !== undefined && v !== null && v.trim() !== "");
  return normalizeLanguage(first);
}
