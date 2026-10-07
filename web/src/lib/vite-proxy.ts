import routes from "../constants/api-routes.generated.json";

interface GeneratedRoute {
  match: "exact" | "prefix";
  path: string;
  port: number;
}

export type ProxyEntry = { target: string; changeOrigin: boolean };

export function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Dev-server proxy table built from the generated route list (conf/routes.yaml).
 * Vite treats a key starting with "^" as a RegExp tested against req.url, which includes the query string,
 * so an exact route must allow an optional query string (WR-20). Prefix keys stay plain path prefixes.
 */
export function buildProxy(): Record<string, ProxyEntry> {
  const proxy: Record<string, ProxyEntry> = {};
  for (const route of routes.routes as GeneratedRoute[]) {
    const key = route.match === "exact" ? `^${escapeRegExp(route.path)}(\\?.*)?$` : route.path;
    proxy[key] = { target: `http://127.0.0.1:${route.port}`, changeOrigin: true };
  }
  return proxy;
}
