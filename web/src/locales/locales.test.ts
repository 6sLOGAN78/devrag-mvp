import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import zh from "@/locales/zh.json";

type Tree = { [k: string]: string | Tree };

export function flatten(tree: Tree, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(tree)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else Object.assign(out, flatten(v, key));
  }
  return out;
}

const placeholders = (s: string) => [...s.matchAll(/{{\s*(\w+)\s*}}/g)].map((m) => m[1]).sort();

export function diffLocales(a: Record<string, string>, b: Record<string, string>) {
  const missingInB = Object.keys(a).filter((k) => !(k in b));
  const missingInA = Object.keys(b).filter((k) => !(k in a));
  const empty = [...Object.entries(a), ...Object.entries(b)].filter(([, v]) => v.trim() === "").map(([k]) => k);
  const placeholderMismatch = Object.keys(a).filter((k) => k in b && placeholders(a[k]!).join() !== placeholders(b[k]!).join());
  return { missingInA, missingInB, empty, placeholderMismatch };
}

describe("locale parity (D-23)", () => {
  const flatEn = flatten(en as Tree);
  const flatZh = flatten(zh as Tree);
  it("has the same keys in en and zh, no empty values, same placeholders", () => {
    expect(diffLocales(flatEn, flatZh)).toEqual({ missingInA: [], missingInB: [], empty: [], placeholderMismatch: [] });
  });
  it("is not vacuous", () => {
    expect(Object.keys(flatEn).length).toBeGreaterThan(10);
  });
  it("detects drift on a fixture", () => {
    const d = diffLocales({ a: "x {{n}}", b: "y", c: "" }, { a: "x", d: "z" });
    expect(d.missingInB).toEqual(["b", "c"]);
    expect(d.missingInA).toEqual(["d"]);
    expect(d.empty).toEqual(["c"]);
    expect(d.placeholderMismatch).toEqual(["a"]);
  });
});
