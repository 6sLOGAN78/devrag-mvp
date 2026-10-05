import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import routes from "./src/constants/api-routes.generated.json";

interface GeneratedRoute {
  match: "exact" | "prefix";
  path: string;
  port: number;
}

function buildProxy(): Record<string, { target: string; changeOrigin: boolean }> {
  const proxy: Record<string, { target: string; changeOrigin: boolean }> = {};
  for (const route of routes.routes as GeneratedRoute[]) {
    const key = route.match === "exact" ? `^${route.path}$` : route.path;
    proxy[key] = { target: `http://127.0.0.1:${route.port}`, changeOrigin: true };
  }
  return proxy;
}

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { proxy: buildProxy() },
});
