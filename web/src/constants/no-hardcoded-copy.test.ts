/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";

/**
 * Grep-style gate for the string system (UI-42, D-23): constants/copy.ts is gone, nothing imports it, and the
 * migrated files carry no hard-coded user-facing English. Sources are read as raw text at build time.
 */
const all = import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const production = Object.entries(all).filter(([path]) => !/\.test\.(ts|tsx)$/.test(path) && !path.includes("/src/test/"));

const MIGRATED = ["/src/pages/system-status/index.tsx", "/src/pages/not-found/index.tsx", "/src/pages/route-error/index.tsx", "/src/services/http.ts"];

type Tree = { [k: string]: string | Tree };
function leaves(tree: Tree): string[] {
  return Object.values(tree).flatMap((v) => (typeof v === "string" ? [v] : leaves(v)));
}

/** Strip comments so prose in a comment is not mistaken for UI text. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

export function findHardCodedText(source: string): string[] {
  const text = code(source);
  const hits: string[] = [];
  // JSX text that contains a letter, e.g. <p>Loading</p>
  for (const m of text.matchAll(/>([^<>{}=]*[A-Za-z][^<>{}]*)</g)) if (!/^\s*$/.test(m[1]!) && !/=>|\?|&&/.test(m[1]!)) hits.push(`jsx text: ${m[1]!.trim()}`);
  // text-bearing attributes and toast fields with a literal containing a letter
  for (const m of text.matchAll(/\b(title|description|aria-label|placeholder|alt|label|heading|body|actionLabel)\s*[=:]\s*(?:"([^"]*[A-Za-z][^"]*)"|'([^']*[A-Za-z][^']*)'|`([^`]*[A-Za-z][^`]*)`)/g)) {
    hits.push(`${m[1]}: ${m[2] ?? m[3] ?? m[4]}`);
  }
  // any whole locale value used as a string literal
  for (const value of leaves(en as Tree)) {
    if (value.length < 5) continue;
    const chunk = value.split(/{{\s*\w+\s*}}/).sort((a, b) => b.length - a.length)[0]!.trim();
    if (chunk.length >= 5 && ["\"", "'", "`", ">"].some((q) => text.includes(`${q}${chunk}`))) hits.push(`locale text: ${chunk}`);
  }
  return hits;
}

describe("single string system", () => {
  it("is not vacuous: the scan sees the migrated files", () => {
    for (const path of MIGRATED) expect(all[path], path).toBeTypeOf("string");
    expect(production.length).toBeGreaterThan(20);
  });

  it("no production file imports constants/copy and the file is gone", () => {
    expect(Object.keys(all)).not.toContain("/src/constants/copy.ts");
    expect(production.filter(([, source]) => /constants\/copy/.test(source)).map(([path]) => path)).toEqual([]);
  });

  it("the migrated files contain no hard-coded user-facing English", () => {
    for (const path of MIGRATED) expect({ path, hits: findHardCodedText(all[path]!) }).toEqual({ path, hits: [] });
  });

  it("the detector catches the old patterns (fixture)", () => {
    expect(findHardCodedText('<p className="x">Checking services</p>')).toContain("jsx text: Checking services");
    expect(findHardCodedText('notifyError({ title: "Request failed" })')).toContain("title: Request failed");
    expect(findHardCodedText('const label = "Request failed";')).toContain("locale text: Request failed");
    expect(findHardCodedText('const a = t("status.title"); // System status\n<p>{a}</p>')).toEqual([]);
    expect(findHardCodedText('<Button aria-label="Close" />').length).toBeGreaterThan(0);
  });
});
