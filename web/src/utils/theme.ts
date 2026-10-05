export type ThemeChoice = "light" | "dark" | "system";

export const THEME_KEY = "devrag.theme";

export function getThemeChoice(): ThemeChoice {
  const stored = localStorage.getItem(THEME_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

function prefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function applyTheme(choice: ThemeChoice): void {
  const dark = choice === "dark" || (choice === "system" && prefersDark());
  document.documentElement.classList.toggle("dark", dark);
}

export function setThemeChoice(choice: ThemeChoice): void {
  if (choice === "system") localStorage.removeItem(THEME_KEY);
  else localStorage.setItem(THEME_KEY, choice);
  applyTheme(choice);
}
