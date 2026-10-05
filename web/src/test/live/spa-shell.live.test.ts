import { describe, expect, it } from "vitest";
import { waitUntil } from "@/test/wait-until";

// Runs against the real ingress (LIVE_BASE_URL, default http://127.0.0.1:8080). Needs the stack from plan 01-13/01-15.
const origin = window.location.origin;
const url = (path: string) => new URL(path, origin).toString();

async function getText(path: string): Promise<{ status: number; type: string; text: string }> {
  const response = await fetch(url(path));
  return { status: response.status, type: response.headers.get("content-type") ?? "", text: await response.text() };
}

function assetRefs(html: string): string[] {
  const refs = [...html.matchAll(/<(?:script|link)\b[^>]*?(?:src|href)="(\/[^"]+\.(?:js|css))"/g)].map((m) => m[1]);
  return [...new Set(refs)];
}

describe("live SPA shell through the ingress", () => {
  it("waits for the ingress health route", async () => {
    await waitUntil(async () => (await fetch(url("/health"))).ok, { describe: "GET /health on the ingress", timeout: 60_000 });
  });

  it("serves index.html at / and every referenced asset with the right content type", async () => {
    const page = await getText("/");
    expect(page.status).toBe(200);
    expect(page.type).toContain("text/html");
    expect(page.text).toContain('<div id="root">');
    const refs = assetRefs(page.text);
    expect(refs.length).toBeGreaterThanOrEqual(2);
    for (const ref of refs) {
      const response = await fetch(url(ref));
      expect(response.status, ref).toBe(200);
      const type = response.headers.get("content-type") ?? "";
      expect(type, ref).toMatch(ref.endsWith(".css") ? /text\/css/ : /javascript/);
    }
  });

  it("returns index.html for an unbuilt SPA path such as /datasets", async () => {
    const root = await getText("/");
    const deep = await getText("/datasets");
    expect(deep.status).toBe(200);
    expect(deep.type).toContain("text/html");
    expect(deep.text).toBe(root.text);
  });

  it("references or lazily reaches at least 2 distinct JS assets", async () => {
    const page = await getText("/");
    const scripts = assetRefs(page.text).filter((r) => r.endsWith(".js"));
    expect(scripts.length).toBeGreaterThanOrEqual(1);
    const entry = await getText(scripts[0]);
    const lazy = [...entry.text.matchAll(/assets\/([\w.-]+\.js)/g)].map((m) => `/assets/${m[1]}`);
    const distinct = new Set([...scripts, ...lazy]);
    expect(distinct.size).toBeGreaterThanOrEqual(2);
    for (const asset of distinct) {
      const response = await fetch(url(asset));
      expect(response.status, asset).toBe(200);
      expect(response.headers.get("content-type") ?? "", asset).toMatch(/javascript/);
    }
  });
});
