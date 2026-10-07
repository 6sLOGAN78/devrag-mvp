export type ThemeChoice = "light" | "dark" | "system";

export const THEME_KEY = "devrag.theme";

/** The values of the profile `color_schema` column this app writes (UI-43). */
export type ColourSchema = "Bright" | "Dark";

function readStored(): string | null {
  try {
    return localStorage.getItem(THEME_KEY);
  } catch {
    // Storage blocked (private mode, policy): the page still works, with the system theme.
    return null;
  }
}

/**
 * The one rule for "is this page dark". The inline first-paint script in index.html repeats it (it runs before any
 * module loads), and a unit test runs that script against this function so the two cannot drift.
 */
export function shouldUseDark(stored: string | null, systemDark: boolean): boolean {
  if (stored === "dark") return true;
  if (stored === "light") return false;
  return systemDark;
}

export function getThemeChoice(): ThemeChoice {
  const stored = readStored();
  return stored === "light" || stored === "dark" ? stored : "system";
}

function prefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function applyTheme(choice: ThemeChoice): void {
  document.documentElement.classList.toggle("dark", shouldUseDark(choice === "system" ? null : choice, prefersDark()));
}

export function setThemeChoice(choice: ThemeChoice): void {
  try {
    if (choice === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, choice);
  } catch {
    /* storage unavailable: the choice applies for this page only */
  }
  applyTheme(choice);
}

/** Bright and Dark map to light and dark; System has no column value, so nothing is written for it. */
export function colourSchemaFor(choice: ThemeChoice): ColourSchema | null {
  if (choice === "light") return "Bright";
  if (choice === "dark") return "Dark";
  return null;
}

/**
 * Applies the signed-in user's saved `color_schema` when this browser has no stored choice (localStorage is
 * authoritative). Only "Dark" carries a signal: "Bright" is the column default for every account, so it is not
 * allowed to override a dark system theme. Nothing is persisted, so a later explicit choice still wins.
 */
export function applyUserColourSchema(value: string | null | undefined): void {
  if (readStored() !== null || value !== "Dark") return;
  applyTheme("dark");
}
