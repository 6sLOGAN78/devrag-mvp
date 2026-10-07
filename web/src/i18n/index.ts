import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "@/locales/en.json";
import zh from "@/locales/zh.json";
import { detectLanguage, LANG_KEY, normalizeLanguage, type Language } from "./language";

function readStored(): string | null {
  try {
    return localStorage.getItem(LANG_KEY);
  } catch {
    return null;
  }
}

export function initialLanguage(): Language {
  return detectLanguage({ stored: readStored(), navigatorLanguage: typeof navigator === "undefined" ? null : navigator.language });
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, zh: { translation: zh } },
  supportedLngs: ["en", "zh"],
  lng: initialLanguage(),
  fallbackLng: "en",
  // React escapes rendered text and translated output is never set as raw HTML (T-02-46).
  interpolation: { escapeValue: false },
  initImmediate: false,
});

document.documentElement.lang = i18n.language;

/** Switch language, persist the choice and keep <html lang> in sync (drives the CJK font stack). */
export async function setLanguage(code: string): Promise<Language> {
  const lang = normalizeLanguage(code);
  await i18n.changeLanguage(lang);
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    /* storage unavailable: the choice applies for this session only */
  }
  document.documentElement.lang = lang;
  return lang;
}

export default i18n;

/**
 * Applies the signed-in user's language when the visitor has made no explicit local choice (UI-07).
 * It does not persist anything, so a later explicit choice still wins.
 */
export function applyUserLanguage(language: string | null | undefined): void {
  if (readStored() !== null || !language || language.trim() === "") return;
  const lang = normalizeLanguage(language);
  if (lang === i18n.language) return;
  void i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
}
