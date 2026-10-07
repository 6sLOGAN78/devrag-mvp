/// <reference types="vite/client" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import indexHtml from "../../index.html?raw";
import { applyTheme, applyUserColourSchema, colourSchemaFor, getThemeChoice, setThemeChoice, shouldUseDark, THEME_KEY } from "./theme";

function stubMatchMedia(dark: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: dark && query.includes("dark"), media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
}
const isDark = () => document.documentElement.classList.contains("dark");

beforeEach(() => {
  document.documentElement.classList.remove("dark");
  stubMatchMedia(false);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.documentElement.classList.remove("dark");
});

describe("shouldUseDark (shared by theme.ts and the first-paint script)", () => {
  it.each([
    ["dark", false, true],
    ["dark", true, true],
    ["light", true, false],
    ["light", false, false],
    ["system", true, true],
    ["system", false, false],
    [null, true, true],
    [null, false, false],
    ["garbage", true, true],
    ["", false, false],
  ] as const)("stored %j, system dark %s -> dark %s", (stored, system, expected) => {
    expect(shouldUseDark(stored, system)).toBe(expected);
  });
});

describe("theme choice storage", () => {
  it("reads and writes devrag.theme and applies the class", () => {
    setThemeChoice("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(isDark()).toBe(true);
    expect(getThemeChoice()).toBe("dark");
    setThemeChoice("light");
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
    expect(isDark()).toBe(false);
    setThemeChoice("system");
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
    expect(getThemeChoice()).toBe("system");
  });

  it("follows the system when the choice is system", () => {
    stubMatchMedia(true);
    applyTheme("system");
    expect(isDark()).toBe(true);
    stubMatchMedia(false);
    applyTheme("system");
    expect(isDark()).toBe(false);
  });

  it("does not break when storage is blocked: reads fall back to system, writes still apply the theme", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(getThemeChoice()).toBe("system");
    expect(() => setThemeChoice("dark")).not.toThrow();
    expect(isDark()).toBe(true);
    expect(() => setThemeChoice("system")).not.toThrow();
  });
});

describe("profile column mapping (UI-43)", () => {
  it("maps Bright and Dark, and writes nothing for System", () => {
    expect(colourSchemaFor("light")).toBe("Bright");
    expect(colourSchemaFor("dark")).toBe("Dark");
    expect(colourSchemaFor("system")).toBeNull();
  });

  it("applies a server Dark only when this browser has no stored choice, and never persists it", () => {
    applyUserColourSchema("Dark");
    expect(isDark()).toBe(true);
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("leaves an explicit local choice alone: localStorage is authoritative", () => {
    localStorage.setItem(THEME_KEY, "light");
    applyUserColourSchema("Dark");
    expect(isDark()).toBe(false);
    localStorage.setItem(THEME_KEY, "dark");
    applyTheme("dark");
    applyUserColourSchema("Bright");
    expect(isDark()).toBe(true);
  });

  it("treats Bright (the column default), empty and unknown values as no signal", () => {
    stubMatchMedia(true);
    for (const value of ["Bright", "", "Blue", null, undefined]) {
      document.documentElement.classList.remove("dark");
      applyUserColourSchema(value);
      expect(isDark()).toBe(false);
    }
  });

  it("is safe when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(() => applyUserColourSchema("Dark")).not.toThrow();
  });
});

describe("first-paint script in index.html (no theme flash)", () => {
  const script = /<script>([\s\S]*?)<\/script>/.exec(indexHtml)?.[1] ?? "";

  function run(stored: string | null, systemDark: boolean, options: { throwing?: boolean } = {}): boolean {
    const classes = new Set<string>();
    const root = { classList: { add: (c: string) => void classes.add(c) } };
    const storage = {
      getItem: (key: string) => {
        if (options.throwing) throw new DOMException("blocked", "SecurityError");
        return key === THEME_KEY ? stored : null;
      },
    };
    const win = { matchMedia: (query: string) => ({ matches: systemDark && query.includes("dark") }) };
    new Function("localStorage", "window", "document", script)(storage, win, { documentElement: root });
    return classes.has("dark");
  }

  it("exists inline, with no external file and no network", () => {
    expect(script).not.toBe("");
    expect(script).toContain("devrag.theme");
    expect(script).not.toMatch(/fetch|XMLHttpRequest|import\(|src=/);
    expect(indexHtml).not.toMatch(/<script[^>]*src="(?!\/src\/main\.tsx)/);
  });

  it.each([
    ["dark", false],
    ["dark", true],
    ["light", true],
    ["light", false],
    ["system", true],
    ["system", false],
    [null, true],
    [null, false],
    ["garbage", true],
  ] as const)("agrees with shouldUseDark for stored %j, system dark %s", (stored, systemDark) => {
    expect(run(stored, systemDark)).toBe(shouldUseDark(stored, systemDark));
  });

  it("does not throw when storage is blocked", () => {
    expect(() => run(null, true, { throwing: true })).not.toThrow();
  });
});
