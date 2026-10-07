import { describe, expect, it } from "vitest";
import routes from "@/constants/api-routes.generated.json";
import { buildProxy, escapeRegExp } from "@/lib/vite-proxy";

interface GeneratedRoute {
  match: "exact" | "prefix";
  path: string;
  port: number;
}

const all = routes.routes as GeneratedRoute[];
const exact = all.filter((r) => r.match === "exact");
const prefix = all.filter((r) => r.match === "prefix");
const proxy = buildProxy();

// Vite tests a key that starts with "^" as a RegExp against req.url, which includes the query string.
function keyFor(path: string): string {
  const keys = Object.keys(proxy).filter((k) => k.startsWith("^") && new RegExp(k).test(path));
  expect(keys, `a proxy key for ${path}`).toHaveLength(1);
  return keys[0]!;
}

describe("vite dev proxy keys (WR-20)", () => {
  it("is not vacuous: the generated routes contain Go exact paths", () => {
    expect(exact.some((r) => r.port === routes.ports.go_api)).toBe(true);
    expect(Object.keys(proxy)).toHaveLength(all.length);
  });

  it.each(exact.map((r) => [r.path, r.port] as const))("exact %s matches with and without a query string", (path, port) => {
    const keyText = keyFor(path);
    const key = new RegExp(keyText);
    expect(key.test(`${path}?page=1&page_size=10`)).toBe(true);
    expect(key.test(`${path}?`)).toBe(true);
    expect(key.test(`${path}x`)).toBe(false);
    expect(key.test(`${path}/`)).toBe(false);
    expect(key.test(`${path}/child`)).toBe(false);
    expect(proxy[keyText]?.target).toBe(`http://127.0.0.1:${port}`);
  });

  it("escapes regex metacharacters so a dot in a path is literal", () => {
    expect(new RegExp(`^${escapeRegExp("/a.b+c")}(\\?.*)?$`).test("/aXb+c")).toBe(false);
    expect(new RegExp(`^${escapeRegExp("/a.b+c")}(\\?.*)?$`).test("/a.b+c?x=1")).toBe(true);
  });

  it("keeps prefix keys as plain path prefixes", () => {
    for (const r of prefix) expect(proxy[r.path]?.target).toBe(`http://127.0.0.1:${r.port}`);
  });
});
